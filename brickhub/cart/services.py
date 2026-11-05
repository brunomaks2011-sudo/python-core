"""Cart logic shared by views, the context processor and checkout."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from catalog.models import Favorite, Product
from core.utils import money

from .models import Cart, CartItem

SESSION_CART = "cart_id"
SESSION_FAVORITES = "favorites"
SESSION_COMPARE = "compare"
COMPARE_LIMIT = 4


def get_cart(request, create: bool = False) -> Cart | None:
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=request.user)
        return cart
    cart_id = request.session.get(SESSION_CART)
    if cart_id:
        cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
        if cart:
            return cart
    if not create:
        return None
    if not request.session.session_key:
        request.session.save()
    cart = Cart.objects.create(session_key=request.session.session_key)
    request.session[SESSION_CART] = cart.pk
    return cart


def cart_count(request) -> int:
    cart = get_cart(request)
    if not cart:
        return 0
    return sum(CartItem.objects.filter(cart=cart).values_list("quantity", flat=True))


class CartError(Exception):
    pass


def add_product(cart: Cart, product: Product, quantity: int = 1) -> tuple[CartItem, int]:
    """Add up to ``quantity`` items, never more than in stock. Returns (item, really added)."""
    if not product.is_active:
        raise CartError("Цей товар недоступний для замовлення.")
    stock = product.stock
    if stock <= 0:
        raise CartError("На жаль, товару немає в наявності.")
    quantity = max(1, int(quantity))
    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": 0})
        new_qty = min(item.quantity + quantity, stock)
        added = new_qty - item.quantity
        if added <= 0:
            raise CartError(f"У кошику вже максимальна доступна кількість ({stock} шт.).")
        item.quantity = new_qty
        item.save(update_fields=["quantity"])
    cart.save(update_fields=["updated_at"])
    return item, added


def set_quantity(item: CartItem, quantity: int) -> CartItem | None:
    if quantity <= 0:
        item.delete()
        return None
    item.quantity = min(quantity, max(item.product.stock, 1))
    item.save(update_fields=["quantity"])
    return item


@dataclass
class CartSummary:
    items: list = field(default_factory=list)
    count: int = 0
    subtotal: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    promo: object = None
    promo_error: str = ""
    warnings: list = field(default_factory=list)
    free_delivery_from: int = 0
    free_delivery_left: Decimal = Decimal("0")

    @property
    def free_delivery(self) -> bool:
        return bool(self.free_delivery_from) and self.total >= self.free_delivery_from

    @property
    def free_delivery_progress(self) -> int:
        if not self.free_delivery_from:
            return 0
        return min(100, int(self.total / self.free_delivery_from * 100))


def summarize(cart: Cart | None, user=None, email: str = "") -> CartSummary:
    summary = CartSummary(free_delivery_from=settings.SHOP["FREE_DELIVERY_FROM"])
    if not cart:
        return summary
    items = list(
        cart.items.select_related("product", "product__inventory", "product__color", "product__part",
                                  "product__lego_set", "product__minifigure", "product__theme")
        .prefetch_related("product__images")
    )
    for item in items:
        p = item.product
        if not p.is_active:
            summary.warnings.append(f"«{p.title}» більше не продається і буде прибраний із замовлення.")
        elif p.stock < item.quantity:
            if p.stock <= 0:
                summary.warnings.append(f"«{p.title}» закінчився на складі.")
            else:
                summary.warnings.append(f"«{p.title}»: у наявності лише {p.stock} шт., кількість зменшено.")
                item.quantity = p.stock
                item.save(update_fields=["quantity"])
    sellable = [i for i in items if i.product.is_active and i.product.stock > 0]
    summary.items = items
    summary.count = sum(i.quantity for i in sellable)
    summary.subtotal = money(sum((i.line_total for i in sellable), Decimal("0")))
    if cart.promo_id:
        promo = cart.promo
        error = promo.validate_for(sellable, user=user, email=email) if sellable else "Кошик порожній."
        if error:
            summary.promo_error = error
        else:
            summary.promo = promo
            summary.discount = promo.discount_for(sellable)
    summary.total = money(max(Decimal("0"), summary.subtotal - summary.discount))
    if summary.free_delivery_from:
        summary.free_delivery_left = money(max(Decimal("0"), summary.free_delivery_from - summary.total))
    return summary


# ---------------------------------------------------------------------------
# Favourites and comparison (session for guests, database for customers)
# ---------------------------------------------------------------------------
def favorite_ids(request) -> set[int]:
    if request.user.is_authenticated:
        return set(Favorite.objects.filter(user=request.user).values_list("product_id", flat=True))
    return set(request.session.get(SESSION_FAVORITES, []))


def toggle_favorite(request, product: Product) -> bool:
    """Returns True when the product is now in favourites."""
    if request.user.is_authenticated:
        fav, created = Favorite.objects.get_or_create(user=request.user, product=product)
        if not created:
            fav.delete()
        return created
    ids = list(request.session.get(SESSION_FAVORITES, []))
    if product.pk in ids:
        ids.remove(product.pk)
        added = False
    else:
        ids.insert(0, product.pk)
        added = True
    request.session[SESSION_FAVORITES] = ids[:200]
    return added


def compare_ids(request) -> list[int]:
    return list(request.session.get(SESSION_COMPARE, []))


def toggle_compare(request, product: Product) -> tuple[bool, str]:
    ids = compare_ids(request)
    if product.pk in ids:
        ids.remove(product.pk)
        request.session[SESSION_COMPARE] = ids
        return False, ""
    message = ""
    if len(ids) >= COMPARE_LIMIT:
        ids.pop()
        message = f"Порівнювати можна до {COMPARE_LIMIT} товарів — найстаріший прибрано."
    ids.insert(0, product.pk)
    request.session[SESSION_COMPARE] = ids
    return True, message


def merge_session_into_user(request, user) -> None:
    """Called on login: move the guest cart and favourites into the account."""
    cart_id = request.session.get(SESSION_CART)
    if cart_id:
        guest = Cart.objects.filter(pk=cart_id, user__isnull=True).first()
        if guest:
            user_cart, _ = Cart.objects.get_or_create(user=user)
            for item in guest.items.select_related("product__inventory"):
                target, _ = CartItem.objects.get_or_create(cart=user_cart, product=item.product,
                                                           defaults={"quantity": 0})
                target.quantity = min(target.quantity + item.quantity, max(item.product.stock, 1))
                target.save(update_fields=["quantity"])
            if guest.promo_id and not user_cart.promo_id:
                user_cart.promo_id = guest.promo_id
                user_cart.save(update_fields=["promo"])
            guest.delete()
        request.session.pop(SESSION_CART, None)
    fav_ids = request.session.pop(SESSION_FAVORITES, [])
    if fav_ids:
        existing = set(Favorite.objects.filter(user=user).values_list("product_id", flat=True))
        Favorite.objects.bulk_create(
            [Favorite(user=user, product_id=pid) for pid in fav_ids
             if pid not in existing and Product.objects.filter(pk=pid).exists()],
            ignore_conflicts=True,
        )
