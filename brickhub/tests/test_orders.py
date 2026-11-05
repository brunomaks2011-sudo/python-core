import base64
import hashlib
import json
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from cart.models import PromoCode
from catalog.models import Inventory
from orders.models import Order, Payment
from orders.payments.liqpay import LiqPayProvider
from orders.services import change_status
from orders.shipping import NovaPoshtaClient, tracking_url

from .factories import base_catalog, part_product, set_product

CHECKOUT = {
    "first_name": "Іван", "last_name": "Петренко", "phone": "067 123 45 67", "email": "ivan@example.com",
    "delivery_method": "np_warehouse", "city": "Київ", "np_warehouse": "Відділення №1", "payment_method": "cod",
    "agree": "on",
}


class CheckoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.part = part_product(color=cls.colors["red"], qty=50, price="6.00")
        cls.xwing = set_product(qty=2, price="8999")

    def add(self, product, qty=1):
        return self.client.post(reverse("cart:add"), {"product": product.pk, "quantity": qty})

    def test_cart_respects_stock(self):
        r = self.client.post(reverse("cart:add"), {"product": self.xwing.pk, "quantity": 5},
                             HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json()["count"], 2)  # only 2 in stock
        r = self.client.post(reverse("cart:add"), {"product": self.xwing.pk, "quantity": 1},
                             HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.status_code, 400)

    def test_order_flow_decrements_stock_and_sends_mail(self):
        self.add(self.part, 10)
        self.add(self.xwing, 1)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("orders:checkout"), CHECKOUT)
        self.assertEqual(r.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.phone, "+380671234567")
        self.assertEqual(order.subtotal, Decimal("9059.00"))
        self.assertEqual(order.delivery_cost, Decimal("0"))  # above the free delivery threshold
        self.assertEqual(order.status, Order.STATUS_NEW)
        self.assertEqual(Inventory.objects.get(product=self.part).quantity, 40)
        self.assertEqual(Inventory.objects.get(product=self.xwing).quantity, 1)
        self.assertEqual(order.items.count(), 2)
        self.assertTrue(any(order.number in m.subject for m in mail.outbox))
        # success page needs the token
        self.assertEqual(self.client.get(r["Location"]).status_code, 200)
        self.assertEqual(Client_get_without_token(order).status_code, 404)

    def test_cancel_returns_stock(self):
        self.add(self.part, 5)
        self.client.post(reverse("orders:checkout"), CHECKOUT)
        order = Order.objects.get()
        change_status(order, Order.STATUS_CANCELLED, note="test", notify=False)
        self.assertEqual(Inventory.objects.get(product=self.part).quantity, 50)

    def test_promo_codes(self):
        PromoCode.objects.create(code="DETALI15", discount_type="percent", value=15, scope="part", min_order_total=0)
        self.add(self.part, 10)
        self.add(self.xwing, 1)
        self.client.post(reverse("cart:promo"), {"code": "detali15"})
        self.client.post(reverse("orders:checkout"), CHECKOUT)
        order = Order.objects.get()
        self.assertEqual(order.discount_total, Decimal("9.00"))  # 15% of the parts only (60 ₴)
        self.assertEqual(PromoCode.objects.get().used_count, 1)

    def test_promo_min_total(self):
        PromoCode.objects.create(code="BIG", discount_type="fixed", value=100, min_order_total=500)
        self.add(self.part, 1)
        r = self.client.post(reverse("cart:promo"), {"code": "BIG"}, follow=True)
        self.assertContains(r, "Промокод діє для замовлень від")

    def test_card_payment_unavailable_without_keys(self):
        self.add(self.part, 1)
        r = self.client.post(reverse("orders:checkout"), dict(CHECKOUT, payment_method="card"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_ukrposhta_requires_postal_code(self):
        self.add(self.part, 1)
        r = self.client.post(reverse("orders:checkout"), dict(CHECKOUT, delivery_method="ukrposhta",
                                                               address="вул. Хрещатик, 1", postal_code="12"))
        self.assertContains(r, "Індекс складається з 5 цифр")

    def test_quick_order_parsing(self):
        r = self.client.get(reverse("cart:quick_order"), {"lines": "3001 5 3\n3001 Purpleish 2\n99999 1"})
        self.assertContains(r, "Готово до замовлення")
        self.assertContains(r, "Колір «Purpleish» не знайдено")
        self.assertContains(r, "Не знайдено в асортименті")

    def test_tracking_requires_matching_contact(self):
        self.add(self.part, 1)
        self.client.post(reverse("orders:checkout"), CHECKOUT)
        order = Order.objects.get()
        r = self.client.post(reverse("orders:track"), {"number": order.number, "contact": "wrong@example.com"})
        self.assertNotContains(r, "Історія")
        r = self.client.post(reverse("orders:track"), {"number": order.number, "contact": "067-123-45-67"})
        self.assertContains(r, order.number)


def Client_get_without_token(order):
    from django.test import Client

    return Client().get(reverse("orders:success", args=[order.number]))


@override_settings(LIQPAY_PUBLIC_KEY="pub_test", LIQPAY_PRIVATE_KEY="priv_test", LIQPAY_SANDBOX=True)
class LiqPayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()
        cls.part = part_product(qty=10)
        user = User.objects.create_user("buyer@example.com", "Secret-pass-123")
        cls.order = Order.objects.create(user=user, first_name="A", last_name="B", phone="+380671234567",
                                         email="buyer@example.com", delivery_method="np_warehouse", city="Київ",
                                         np_warehouse="1", payment_method="card", payment_status="pending",
                                         status=Order.STATUS_AWAITING_PAYMENT, subtotal=100, total=Decimal("100.00"))

    def _sign(self, payload):
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        sig = base64.b64encode(hashlib.sha1(("priv_test" + data + "priv_test").encode()).digest()).decode()
        return data, sig

    def test_checkout_form_signature(self):
        form = LiqPayProvider().checkout_form(self.order, "https://x/r", "https://x/s")
        params = json.loads(base64.b64decode(form["data"]))
        self.assertEqual(params["amount"], "100.00")
        self.assertEqual(params["currency"], "UAH")
        self.assertEqual(params["sandbox"], 1)
        expected = base64.b64encode(hashlib.sha1(("priv_test" + form["data"] + "priv_test").encode()).digest()).decode()
        self.assertEqual(form["signature"], expected)

    def test_callback_rejects_bad_signature(self):
        data, _ = self._sign({"order_id": self.order.number, "status": "success", "amount": "100.00", "currency": "UAH"})
        r = self.client.post(reverse("orders:liqpay_callback"), {"data": data, "signature": "forged"})
        self.assertEqual(r.status_code, 400)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, "paid")

    def test_callback_rejects_wrong_amount(self):
        data, sig = self._sign({"order_id": self.order.number, "status": "success", "amount": "1.00", "currency": "UAH"})
        self.client.post(reverse("orders:liqpay_callback"), {"data": data, "signature": sig})
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, "paid")

    def test_callback_marks_paid(self):
        data, sig = self._sign({"order_id": self.order.number, "status": "sandbox", "amount": "100.00",
                                "currency": "UAH", "payment_id": 42})
        r = self.client.post(reverse("orders:liqpay_callback"), {"data": data, "signature": sig})
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.order.status, Order.STATUS_PAID)
        self.assertEqual(Payment.objects.get(order=self.order).status, "success")


class NovaPoshtaTests(TestCase):
    def _resp(self, payload):
        m = mock.MagicMock()
        m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return m

    def test_search_cities_and_warehouses(self):
        client = NovaPoshtaClient(api_key="k", url="https://api.example/json/")
        cities = {"success": True, "data": [{"Addresses": [
            {"Present": "м. Київ, Київська обл.", "MainDescription": "Київ", "DeliveryCity": "ref-1", "Warehouses": 3}]}]}
        with mock.patch("urllib.request.urlopen", return_value=self._resp(cities)):
            self.assertEqual(client.search_cities("ки")[0]["ref"], "ref-1")
        whs = {"success": True, "data": [
            {"Ref": "w1", "Number": "1", "Description": "Відділення №1: вул. Тестова, 1", "CategoryOfWarehouse": "Branch"},
            {"Ref": "w2", "Number": "2", "Description": "Поштомат №2", "CategoryOfWarehouse": "Postomat"}]}
        with mock.patch("urllib.request.urlopen", return_value=self._resp(whs)):
            self.assertEqual([w["ref"] for w in client.warehouses("ref-1", kind="branch")], ["w1"])
            self.assertEqual([w["ref"] for w in client.warehouses("ref-1", kind="postomat")], ["w2"])

    def test_api_disabled_without_key(self):
        r = self.client.get("/api/np/mista/", {"q": "Київ"})
        self.assertEqual(r.json(), {"enabled": False, "items": []})

    def test_tracking_urls(self):
        self.assertIn("novaposhta.ua/tracking", tracking_url("np_warehouse", "123"))
        self.assertIn("ukrposhta.ua", tracking_url("ukrposhta", "RR123"))
