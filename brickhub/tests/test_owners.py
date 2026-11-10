"""Whose goods: the shop owner's and the partner's listings, and who sold how much."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from cart.models import PromoCode
from catalog.models import Product
from orders.models import Order, OrderItem
from orders.services import change_status
from panel.owners import sales_by_owner, split_order

from .factories import base_catalog, part_product, set_product
from .test_orders import CHECKOUT


class OwnersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.boss = User.objects.create_superuser("boss@example.com", "Correct-horse-1", first_name="Максим")
        cls.partner = User.objects.create_user("partner@example.com", "Correct-horse-1", is_staff=True,
                                               first_name="Олег")
        cls.part = part_product(color=cls.colors["red"], qty=100, price="10.00")
        cls.xwing = set_product(qty=3, price="900")
        Product.objects.filter(pk=cls.part.pk).update(owner=cls.boss)
        Product.objects.filter(pk=cls.xwing.pk).update(owner=cls.partner)

    def buy(self, *lines, promo=None):
        for product, qty in lines:
            self.client.post(reverse("cart:add"), {"product": product.pk, "quantity": qty})
        if promo:
            self.client.post(reverse("cart:promo"), {"code": promo})
        self.client.post(reverse("orders:checkout"), CHECKOUT)
        return Order.objects.order_by("-pk").first()

    def test_a_new_listing_belongs_to_who_adds_it(self):
        self.client.force_login(self.partner)
        form = self.client.get(reverse("panel:product_new") + "?kind=keychain").context["form"]
        self.assertEqual(form.initial["owner"], self.partner.pk)
        self.client.post(reverse("panel:product_new"), {
            "kind": "keychain", "condition": "new", "title": "Брелок Олега", "price": "300", "quantity": 1,
            "owner": self.partner.pk, "is_active": "on"})
        self.assertEqual(Product.objects.get(title="Брелок Олега").owner, self.partner)

    def test_labels_filter_and_bulk_assign_in_the_panel(self):
        self.client.force_login(self.boss)
        page = self.client.get(reverse("panel:products")).content.decode()
        self.assertIn('class="owner" style="--c:#2f6fcf"', page)   # the shop owner's colour
        self.assertIn(">Олег</span>", page)
        listed = self.client.get(reverse("panel:products") + f"?owner={self.partner.pk}").context["page"].object_list
        self.assertEqual([p.pk for p in listed], [self.xwing.pk])
        self.client.post(reverse("panel:product_bulk"), {"ids": [self.part.pk], "action": "set_owner",
                                                         "owner": self.partner.pk})
        self.assertEqual(Product.objects.get(pk=self.part.pk).owner, self.partner)
        self.client.post(reverse("panel:product_bulk"), {"ids": [self.part.pk], "action": "set_owner", "owner": "none"})
        self.assertIsNone(Product.objects.get(pk=self.part.pk).owner)
        self.assertEqual(list(self.client.get(reverse("panel:products") + "?owner=none").context["page"].object_list),
                         [Product.objects.get(pk=self.part.pk)])
        export = b"".join(self.client.get(reverse("panel:export_products")).streaming_content).decode("utf-8-sig")
        self.assertIn("partner@example.com", export)

    def test_sales_are_split_by_whose_goods_they_were(self):
        PromoCode.objects.create(code="ALL10", discount_type="fixed", value=100, scope="all", min_order_total=0)
        order = self.buy((self.part, 10), (self.xwing, 1), promo="ALL10")
        self.assertEqual(order.discount_total, Decimal("100"))
        self.assertEqual({i.sku: i.owner_id for i in order.items.all()},
                         {self.part.sku: self.boss.pk, self.xwing.sku: self.partner.pk})
        # goods 100 + 900, discount 100 shared 10 % / 90 %
        split = split_order(order)
        self.assertEqual(split[self.boss.pk]["amount"], Decimal("90.00"))
        self.assertEqual(split[self.partner.pk]["amount"], Decimal("810.00"))
        stats = sales_by_owner()
        self.assertEqual((stats[self.boss.pk]["amount"], stats[self.boss.pk]["qty"]), (Decimal("90.00"), 10))
        self.assertEqual(stats[self.partner.pk]["orders"], 1)
        # changing the owner later does not rewrite a past sale
        Product.objects.filter(pk=self.xwing.pk).update(owner=self.boss)
        self.assertEqual(sales_by_owner()[self.partner.pk]["amount"], Decimal("810.00"))

        self.client.force_login(self.boss)
        dash = self.client.get(reverse("panel:dashboard")).content.decode()
        self.assertIn("Продажі за власниками товарів", dash)
        self.assertIn("810", dash)
        detail = self.client.get(reverse("panel:order_detail", args=[order.pk])).content.decode()
        self.assertIn("Чиї товари в замовленні", detail)
        # a cancelled order is not a sale
        change_status(order, Order.STATUS_CANCELLED)
        self.assertEqual(sales_by_owner(), {})

    def test_a_promo_code_for_parts_is_paid_by_the_owner_of_the_parts(self):
        PromoCode.objects.create(code="PARTS20", discount_type="percent", value=20, scope="part", min_order_total=0)
        order = self.buy((self.part, 10), (self.xwing, 1), promo="PARTS20")
        self.assertEqual(order.discount_total, Decimal("20.00"))
        split = split_order(order)
        self.assertEqual(split[self.boss.pk]["amount"], Decimal("80.00"))
        self.assertEqual(split[self.partner.pk]["amount"], Decimal("900.00"))

    def test_older_sales_fall_back_to_the_listing_owner(self):
        order = self.buy((self.xwing, 1))
        OrderItem.objects.filter(order=order).update(owner=None)  # sold before owners were recorded
        self.assertEqual(sales_by_owner()[self.partner.pk]["amount"], Decimal("900.00"))
