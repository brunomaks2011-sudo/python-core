"""Order placement and status changes."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from cart.models import PromoCode
from cart.services import summarize
from catalog.models import Inventory, InventoryMovement, Product
from core.utils import client_ip, money

from .models import Order, OrderItem, OrderStatusEvent

logger = logging.getLogger("brickhub")


class CheckoutError(Exception):
    pass


def delivery_cost_for(total: Decimal, method: str):
    """0 when the shop pays for delivery, otherwise None = carrier tariff paid on receipt."""
    threshold = settings.SHOP["FREE_DELIVERY_FROM"]
    if threshold and total >= threshold and method in Order.NOVA_POSHTA_METHODS | {Order.DELIVERY_UKRPOSHTA}:
        return Decimal("0")
    return None


def place_order(request, cart, data: dict, user=None) -> Order:
    summary = summarize(cart, user=user, email=data["email"])
    sellable = [i for i in summary.items if i.product.is_active and i.product.stock > 0]
    if not sellable:
        raise CheckoutError("Кошик порожній або товари закінчилися.")
    with transaction.atomic():
        ids = [i.product_id for i in sellable]
        locked = {inv.product_id: inv for inv in Inventory.objects.select_for_update().filter(product_id__in=ids)}
        for item in sellable:
            inv = locked.get(item.product_id)
            if inv is None or inv.quantity < item.quantity:
                available = inv.quantity if inv else 0
                raise CheckoutError(
                    f"«{item.product.title}»: у наявності лише {available} шт. Оновіть кількість у кошику.")
        promo = summary.promo
        if promo:
            promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
            error = promo.validate_for(sellable, user=user, email=data["email"])
            if error:
                raise CheckoutError(error)
        subtotal = money(sum((i.line_total for i in sellable), Decimal("0")))
        discount = promo.discount_for(sellable) if promo else Decimal("0")
        goods_total = max(Decimal("0"), subtotal - discount)
        delivery_cost = delivery_cost_for(goods_total, data["delivery_method"])
        card = data["payment_method"] == Order.PAYMENT_CARD
        order = Order(
            user=user if user and user.is_authenticated else None,
            status=Order.STATUS_AWAITING_PAYMENT if card else Order.STATUS_NEW,
            first_name=data["first_name"].strip(), last_name=data["last_name"].strip(), phone=data["phone"],
            email=data["email"], delivery_method=data["delivery_method"], city=data["city"].strip(),
            city_ref=data.get("city_ref", ""), np_warehouse=data.get("np_warehouse", "").strip(),
            np_warehouse_ref=data.get("np_warehouse_ref", ""), address=data.get("address", "").strip(),
            postal_code=data.get("postal_code", "").strip(), payment_method=data["payment_method"],
            payment_status="pending" if card else "on_delivery", subtotal=subtotal, discount_total=discount,
            delivery_cost=delivery_cost, total=goods_total + (delivery_cost or 0),
            promo_code=promo.code if promo else "", comment=data.get("comment", "").strip(),
            ip_address=client_ip(request) or None,
        )
        for attempt in range(5):
            try:
                with transaction.atomic():
                    order.number = ""
                    order.save()
                break
            except IntegrityError:
                if attempt == 4:
                    raise
        items = []
        for item in sellable:
            p = item.product
            items.append(OrderItem(order=order, product=p, sku=p.sku, title=p.title, kind=p.kind,
                                   number=p.official_number, color_name=p.color.display_name if p.color_id else "",
                                   condition=p.condition, unit_price=p.price, quantity=item.quantity))
            inv = locked[p.pk]
            inv.quantity -= item.quantity
            inv.save(update_fields=["quantity", "updated_at"])
            InventoryMovement.objects.create(inventory=inv, change=-item.quantity, quantity_after=inv.quantity,
                                             reason="order", order=order, user=order.user)
            Product.objects.filter(pk=p.pk).update(sold_count=F("sold_count") + item.quantity)
        OrderItem.objects.bulk_create(items)
        if promo:
            PromoCode.objects.filter(pk=promo.pk).update(used_count=F("used_count") + 1)
        OrderStatusEvent.objects.create(order=order, status=order.status,
                                        note="Замовлення створено на сайті", created_by=order.user)
        cart.items.all().delete()
        cart.promo = None
        cart.save(update_fields=["promo"])
        from .emails import send_new_order_emails

        transaction.on_commit(lambda: send_new_order_emails(order.pk))
    return order


def change_status(order: Order, status: str, note: str = "", by=None, notify: bool = True,
                  visible: bool = True) -> Order:
    if status not in dict(Order.STATUSES):
        raise ValueError(status)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        previous = order.status
        if previous == status and not note:
            return order
        restock = status in (Order.STATUS_CANCELLED, Order.STATUS_RETURNED) and previous not in (
            Order.STATUS_CANCELLED, Order.STATUS_RETURNED)
        order.status = status
        if status == Order.STATUS_PAID:
            order.payment_status = "paid"
        if status == Order.STATUS_DELIVERED and order.payment_method == Order.PAYMENT_COD:
            order.payment_status = "paid"
        order.save(update_fields=["status", "payment_status", "updated_at"])
        if restock:
            for item in order.items.select_related("product"):
                if not item.product_id:
                    continue
                inv = Inventory.objects.select_for_update().get_or_create(product_id=item.product_id)[0]
                inv.quantity += item.quantity
                inv.save()
                InventoryMovement.objects.create(
                    inventory=inv, change=item.quantity, quantity_after=inv.quantity,
                    reason="cancel" if status == Order.STATUS_CANCELLED else "return", order=order, user=by)
                Product.objects.filter(pk=item.product_id, sold_count__gte=item.quantity).update(
                    sold_count=F("sold_count") - item.quantity)
        event = OrderStatusEvent.objects.create(order=order, status=status, note=note, created_by=by,
                                                is_customer_visible=visible, created_at=timezone.now())
        if notify and previous != status:
            from .emails import send_status_email

            transaction.on_commit(lambda: send_status_email(order.pk, event.pk))
    return order
