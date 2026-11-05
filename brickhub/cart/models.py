from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from catalog.models import Product
from core.utils import money


class PromoCode(models.Model):
    TYPE_PERCENT, TYPE_FIXED = "percent", "fixed"
    TYPES = [(TYPE_PERCENT, "Відсоток"), (TYPE_FIXED, "Фіксована сума, ₴")]
    SCOPES = [
        ("all", "Усі товари"),
        ("set", "Лише набори"),
        ("part", "Лише деталі"),
        ("minifig", "Лише мініфігурки"),
    ]

    code = models.CharField("Код", max_length=40, unique=True)
    description = models.CharField("Опис", max_length=255, blank=True)
    discount_type = models.CharField("Тип знижки", max_length=8, choices=TYPES, default=TYPE_PERCENT)
    value = models.DecimalField("Розмір знижки", max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.01"))])
    scope = models.CharField("Діє на", max_length=8, choices=SCOPES, default="all")
    min_order_total = models.DecimalField("Мінімальна сума замовлення, ₴", max_digits=10, decimal_places=2,
                                          default=0)
    max_uses = models.PositiveIntegerField("Ліміт використань", null=True, blank=True)
    used_count = models.PositiveIntegerField("Використано", default=0)
    once_per_user = models.BooleanField("Один раз на покупця", default=False)
    valid_from = models.DateTimeField("Діє з", null=True, blank=True)
    valid_to = models.DateTimeField("Діє до", null=True, blank=True)
    is_active = models.BooleanField("Активний", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "промокод"
        verbose_name_plural = "промокоди"

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        if self.discount_type == self.TYPE_PERCENT:
            return f"−{self.value.normalize():f}%"
        from core.utils import format_uah

        return f"−{format_uah(self.value)}"

    def eligible_subtotal(self, items) -> Decimal:
        total = Decimal("0")
        for item in items:
            if self.scope == "all" or item.product.kind == self.scope:
                total += item.line_total
        return total

    def validate_for(self, items, user=None, email: str = "") -> str:
        """Return an error message, or '' when the code can be applied."""
        now = timezone.now()
        if not self.is_active:
            return "Промокод неактивний."
        if self.valid_from and now < self.valid_from:
            return "Промокод ще не діє."
        if self.valid_to and now > self.valid_to:
            return "Термін дії промокоду завершився."
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return "Ліміт використань промокоду вичерпано."
        subtotal = sum((i.line_total for i in items), Decimal("0"))
        if subtotal < self.min_order_total:
            from core.utils import format_uah

            return f"Промокод діє для замовлень від {format_uah(self.min_order_total)}."
        if self.eligible_subtotal(items) <= 0:
            return "У кошику немає товарів, на які діє цей промокод."
        if self.once_per_user and (user and user.is_authenticated or email):
            from orders.models import Order

            used = Order.objects.filter(promo_code=self.code).exclude(status=Order.STATUS_CANCELLED)
            if user and user.is_authenticated:
                used = used.filter(user=user)
            else:
                used = used.filter(email__iexact=email)
            if used.exists():
                return "Ви вже використали цей промокод."
        return ""

    def discount_for(self, items) -> Decimal:
        base = self.eligible_subtotal(items)
        if base <= 0:
            return Decimal("0")
        if self.discount_type == self.TYPE_PERCENT:
            pct = min(self.value, Decimal("100"))
            return money(base * pct / 100)
        return money(min(self.value, base))


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                related_name="cart")
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    promo = models.ForeignKey(PromoCode, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "кошик"
        verbose_name_plural = "кошики"

    def __str__(self):
        return f"Кошик #{self.pk}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="+", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_product")]

    @property
    def unit_price(self) -> Decimal:
        return self.product.price

    @property
    def line_total(self) -> Decimal:
        return money(self.product.price * self.quantity)
