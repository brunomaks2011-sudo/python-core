"""Whose goods: the people who own listings (the shop owner, partners) and their sales.

Every listing has an owner («Чий товар»). An order item remembers the owner at the moment of the sale, so a
later change of the listing's owner does not rewrite past sales; items sold before owners were recorded fall
back to the listing's current owner.

A promo-code discount is shared between the owners in proportion to their goods that the code applied to
(a code for parts only is paid by the owners of the parts). Delivery is not part of anyone's sales.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, Lower

from cart.models import PromoCode
from orders.models import Order, OrderItem

# Distinct, readable label colours; the shop owner gets the first one.
PALETTE = ["#2f6fcf", "#e8590c", "#7048e8", "#0ca678", "#d6336c", "#1098ad", "#f08c00", "#5c940d"]
REVENUE_STATUSES = [s for s, _ in Order.STATUSES if s not in (Order.STATUS_CANCELLED, Order.STATUS_RETURNED)]
CENT = Decimal("0.01")


def owner_name(user) -> str:
    return ((user.first_name or "").strip() or user.get_full_name().strip() or user.email.split("@")[0]
            or f"#{user.pk}")


def owner_people() -> list[dict]:
    """Staff and anyone who owns listings, shop owner first: [{pk, name, color, role, email, is_staff}]."""
    User = get_user_model()
    users = (User.objects.filter(Q(is_staff=True) | Q(owned_products__isnull=False)).distinct()
             .order_by("-is_superuser", "pk"))
    people = []
    for i, user in enumerate(users):
        role = "Власник магазину" if user.is_superuser else ("Персонал" if user.is_staff else "Без доступу до панелі")
        people.append({"pk": user.pk, "name": owner_name(user), "color": PALETTE[i % len(PALETTE)], "role": role,
                       "email": user.email, "is_staff": user.is_staff})
    return people


def _scopes(codes) -> dict[str, str]:
    codes = {c.lower() for c in codes if c}
    if not codes:
        return {}
    found = PromoCode.objects.annotate(lc=Lower("code")).filter(lc__in=codes).values_list("lc", "scope")
    return dict(found)


def _split(lines, discount, scope) -> dict:
    """lines: [(owner, kind, amount, qty)] of one order -> {owner: {"amount", "qty"}} after the discount."""
    eligible = [line for line in lines if scope in (None, "all") or line[1] == scope]
    if not eligible:
        eligible = lines
    base = sum((line[2] for line in eligible), Decimal("0"))
    out: dict = {}
    for line in lines:
        owner, _kind, amount, qty = line
        if discount and base and line in eligible:
            amount = amount - discount * amount / base
        slot = out.setdefault(owner, {"amount": Decimal("0"), "qty": 0})
        slot["amount"] += amount
        slot["qty"] += qty
    return out


def split_order(order) -> dict:
    """{owner pk or None: {"amount", "qty"}} for one order (any status)."""
    lines = [(item.owner_id or (item.product.owner_id if item.product_id and item.product else None), item.kind,
              item.line_total, item.quantity) for item in order.items.all()]
    scope = _scopes([order.promo_code]).get((order.promo_code or "").lower())
    out = _split(lines, order.discount_total or Decimal("0"), scope)
    for slot in out.values():
        slot["amount"] = slot["amount"].quantize(CENT)
    return out


def sales_by_owner(since=None) -> dict:
    """{owner pk or None: {"amount": Decimal, "qty": int, "orders": int}} over orders that count as sales."""
    items = OrderItem.objects.filter(order__status__in=REVENUE_STATUSES)
    if since is not None:
        items = items.filter(order__created_at__gte=since)
    rows = list(items.annotate(who=Coalesce("owner_id", "product__owner_id", output_field=IntegerField()))
                .values("order_id", "who", "kind")
                .annotate(amount=Sum(F("unit_price") * F("quantity")), qty=Sum("quantity")).order_by())
    by_order: dict = {}
    for row in rows:
        by_order.setdefault(row["order_id"], []).append(
            (row["who"], row["kind"], row["amount"] or Decimal("0"), row["qty"] or 0))
    info = {pk: (discount, code) for pk, discount, code in
            Order.objects.filter(pk__in=by_order.keys(), discount_total__gt=0)
            .values_list("pk", "discount_total", "promo_code")}
    scopes = _scopes(code for _d, code in info.values())
    out: dict = {}
    for order_id, lines in by_order.items():
        discount, code = info.get(order_id, (Decimal("0"), ""))
        for owner, data in _split(lines, discount, scopes.get((code or "").lower())).items():
            slot = out.setdefault(owner, {"amount": Decimal("0"), "qty": 0, "orders": 0})
            slot["amount"] += data["amount"]
            slot["qty"] += data["qty"]
            slot["orders"] += 1
    for slot in out.values():
        slot["amount"] = slot["amount"].quantize(CENT)
    return out
