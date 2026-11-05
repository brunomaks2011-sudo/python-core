from __future__ import annotations

import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PAID = "paid"
    STATUS_ASSEMBLING = "assembling"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_RETURNED = "returned"
    STATUSES = [
        (STATUS_NEW, "Нове"),
        (STATUS_AWAITING_PAYMENT, "Очікує оплату"),
        (STATUS_CONFIRMED, "Підтверджене"),
        (STATUS_PAID, "Оплачене"),
        (STATUS_ASSEMBLING, "Комплектується"),
        (STATUS_SHIPPED, "Відправлене"),
        (STATUS_DELIVERED, "Доставлене"),
        (STATUS_COMPLETED, "Виконане"),
        (STATUS_CANCELLED, "Скасоване"),
        (STATUS_RETURNED, "Повернення"),
    ]
    # Customer facing progress bar.
    TIMELINE = [STATUS_NEW, STATUS_CONFIRMED, STATUS_ASSEMBLING, STATUS_SHIPPED, STATUS_DELIVERED]
    OPEN_STATUSES = {STATUS_NEW, STATUS_AWAITING_PAYMENT, STATUS_CONFIRMED, STATUS_PAID, STATUS_ASSEMBLING}

    DELIVERY_NP_WAREHOUSE = "np_warehouse"
    DELIVERY_NP_POSTOMAT = "np_postomat"
    DELIVERY_NP_COURIER = "np_courier"
    DELIVERY_UKRPOSHTA = "ukrposhta"
    DELIVERY_METHODS = [
        (DELIVERY_NP_WAREHOUSE, "Нова пошта — відділення"),
        (DELIVERY_NP_POSTOMAT, "Нова пошта — поштомат"),
        (DELIVERY_NP_COURIER, "Нова пошта — кур'єр"),
        (DELIVERY_UKRPOSHTA, "Укрпошта"),
    ]
    NOVA_POSHTA_METHODS = {DELIVERY_NP_WAREHOUSE, DELIVERY_NP_POSTOMAT, DELIVERY_NP_COURIER}

    PAYMENT_COD = "cod"
    PAYMENT_CARD = "card"
    PAYMENT_METHODS = [
        (PAYMENT_COD, "Накладений платіж"),
        (PAYMENT_CARD, "Оплата карткою онлайн"),
    ]
    PAYMENT_STATUSES = [
        ("on_delivery", "Оплата при отриманні"),
        ("pending", "Очікує оплату"),
        ("paid", "Оплачено"),
        ("failed", "Помилка оплати"),
        ("refunded", "Повернено"),
    ]

    number = models.CharField("Номер замовлення", max_length=20, unique=True, editable=False)
    access_token = models.CharField(max_length=32, editable=False, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="orders", verbose_name="Покупець")
    status = models.CharField("Статус", max_length=20, choices=STATUSES, default=STATUS_NEW, db_index=True)

    first_name = models.CharField("Ім'я", max_length=80)
    last_name = models.CharField("Прізвище", max_length=80)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("E-mail")

    delivery_method = models.CharField("Спосіб доставки", max_length=20, choices=DELIVERY_METHODS)
    city = models.CharField("Місто / населений пункт", max_length=160)
    city_ref = models.CharField(max_length=64, blank=True)
    np_warehouse = models.CharField("Відділення / поштомат", max_length=255, blank=True)
    np_warehouse_ref = models.CharField(max_length=64, blank=True)
    address = models.CharField("Адреса", max_length=255, blank=True)
    postal_code = models.CharField("Індекс", max_length=10, blank=True)

    payment_method = models.CharField("Спосіб оплати", max_length=10, choices=PAYMENT_METHODS)
    payment_status = models.CharField("Статус оплати", max_length=12, choices=PAYMENT_STATUSES,
                                      default="on_delivery")

    subtotal = models.DecimalField("Сума товарів", max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField("Знижка", max_digits=12, decimal_places=2, default=0)
    delivery_cost = models.DecimalField("Вартість доставки", max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text="Порожньо — за тарифами перевізника")
    total = models.DecimalField("До сплати", max_digits=12, decimal_places=2, default=0)
    promo_code = models.CharField("Промокод", max_length=40, blank=True)

    comment = models.TextField("Коментар покупця", blank=True, max_length=2000)
    admin_note = models.TextField("Нотатка менеджера", blank=True)
    tracking_number = models.CharField("ТТН / трек-номер", max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField("Створено", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("Оновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "замовлення"
        verbose_name_plural = "замовлення"

    def __str__(self):
        return f"Замовлення {self.number}"

    def save(self, *args, **kwargs):
        if not self.access_token:
            self.access_token = secrets.token_hex(16)
        if not self.number:
            self.number = self._next_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _next_number() -> str:
        prefix = timezone.localdate().strftime("%y%m")
        last = Order.objects.filter(number__startswith=f"BH{prefix}").order_by("-number").values_list(
            "number", flat=True).first()
        seq = int(last[-4:]) + 1 if last else 1
        return f"BH{prefix}{seq:04d}"

    # ----- helpers ------------------------------------------------------
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_nova_poshta(self) -> bool:
        return self.delivery_method in self.NOVA_POSHTA_METHODS

    @property
    def delivery_summary(self) -> str:
        if self.delivery_method in (self.DELIVERY_NP_WAREHOUSE, self.DELIVERY_NP_POSTOMAT):
            return f"{self.city}, {self.np_warehouse}"
        parts = [self.postal_code, self.city, self.address]
        return ", ".join(p for p in parts if p)

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def can_cancel(self) -> bool:
        return self.status in {self.STATUS_NEW, self.STATUS_AWAITING_PAYMENT, self.STATUS_CONFIRMED}

    @property
    def items_count(self) -> int:
        return sum(i.quantity for i in self.items.all())

    @property
    def timeline(self) -> list[dict]:
        """Steps for the customer progress bar."""
        order = self.TIMELINE
        current = self.status
        if current in (self.STATUS_AWAITING_PAYMENT,):
            current = self.STATUS_NEW
        if current == self.STATUS_PAID:
            current = self.STATUS_CONFIRMED
        if current == self.STATUS_COMPLETED:
            current = self.STATUS_DELIVERED
        idx = order.index(current) if current in order else -1
        labels = dict(self.STATUSES)
        return [{"code": code, "label": labels[code], "done": i <= idx, "current": i == idx}
                for i, code in enumerate(order)]

    @property
    def tracking_url(self) -> str:
        if not self.tracking_number:
            return ""
        from .shipping import tracking_url

        return tracking_url(self.delivery_method, self.tracking_number)

    def get_absolute_url(self):
        return reverse("accounts:order_detail", args=[self.number])

    def recalc(self):
        self.subtotal = sum((i.line_total for i in self.items.all()), Decimal("0"))
        self.total = max(Decimal("0"), self.subtotal - self.discount_total) + (self.delivery_cost or 0)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items")
    # Snapshot: an order must not change when the product is edited later.
    sku = models.CharField("Артикул", max_length=60)
    title = models.CharField("Назва", max_length=255)
    kind = models.CharField(max_length=12)
    number = models.CharField("Номер LEGO", max_length=40, blank=True)
    color_name = models.CharField("Колір", max_length=64, blank=True)
    condition = models.CharField("Стан", max_length=8, default="new")
    unit_price = models.DecimalField("Ціна", max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField("Кількість")

    class Meta:
        verbose_name = "позиція замовлення"
        verbose_name_plural = "позиції замовлення"

    def __str__(self):
        return f"{self.sku} × {self.quantity}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def condition_label(self) -> str:
        return dict(Product.CONDITIONS).get(self.condition, self.condition)


class OrderStatusEvent(models.Model):
    order = models.ForeignKey(Order, related_name="events", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Order.STATUSES)
    note = models.CharField("Коментар", max_length=500, blank=True)
    is_customer_visible = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "подія замовлення"
        verbose_name_plural = "історія замовлення"


class Payment(models.Model):
    STATUSES = [
        ("created", "Створено"),
        ("pending", "Очікує"),
        ("success", "Успішно"),
        ("failure", "Помилка"),
        ("reversed", "Повернено"),
    ]
    order = models.ForeignKey(Order, related_name="payments", on_delete=models.CASCADE)
    provider = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="UAH")
    status = models.CharField(max_length=10, choices=STATUSES, default="created")
    external_id = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "платіж"
        verbose_name_plural = "платежі"
