"""The owner chooses whether buyers see stock counts; buyers can never take more than the stock."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Inventory, Product

from .factories import base_catalog, part_product, set_product


class StockDisplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("stock@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.set = set_product(qty=37, price="2499")
        self.part = part_product(design="3001", color=self.colors["red"], qty=1234)

    def page(self, product):
        return self.client.get(product.get_absolute_url()).content.decode()

    def test_counts_are_hidden_unless_the_owner_shows_them(self):
        html = self.page(self.set)
        self.assertIn('class="pdx-avail is-in">Є в наявності', html)
        self.assertNotIn("37 шт", html)
        Product.objects.filter(pk=self.set.pk).update(show_stock=True)
        self.assertIn('class="pdx-avail is-in">В наявності: 37 шт.', self.page(self.set))
        Product.objects.filter(pk=self.set.pk).update(availability=Product.AVAILABILITY_LOW)
        self.assertIn('class="pdx-avail is-low">Закінчується: 37 шт.', self.page(self.set))
        Inventory.objects.filter(product=self.set).update(quantity=0)
        self.assertIn('class="pdx-avail is-out">Немає в наявності', self.page(self.set))

    def test_shown_counts_reach_cards_and_the_part_table(self):
        Product.objects.filter(pk=self.part.pk).update(show_stock=True)
        listing = self.client.get(reverse("catalog:category", args=["detali"])).content.decode()
        self.assertIn("В наявності: 1234 шт.", listing)
        table = self.client.get(reverse("catalog:part_design", args=["3001"])).content.decode()
        self.assertIn("В наявності: 1234 шт.", table)
        self.assertIn('max="1234" data-limit="У наявності 1234 шт."', table)

    def test_search_suggestions_never_send_the_number(self):
        data = self.client.get(reverse("catalog:suggest"), {"q": "X-Wing"}).json()
        self.assertTrue(data["items"])
        self.assertNotIn("stock", data["items"][0])
        self.assertTrue(data["items"][0]["in_stock"])

    def test_stepper_stops_at_the_stock(self):
        html = self.page(self.set)
        self.assertIn('max="37" data-limit="Більше немає в наявності"', html)
        Product.objects.filter(pk=self.set.pk).update(show_stock=True)
        self.assertIn('max="37" data-limit="У наявності 37 шт."', self.page(self.set))

    def test_cart_takes_no_more_than_the_stock(self):
        headers = {"HTTP_X_REQUESTED_WITH": "fetch"}
        r = self.client.post(reverse("cart:add"), {"product": self.set.pk, "quantity": 50}, **headers)
        self.assertEqual(r.json()["count"], 37)
        self.assertIn("більше немає в наявності", r.json()["message"])
        self.assertNotIn("лише", r.json()["message"])  # how many were added, not how many the shop has
        r = self.client.post(reverse("cart:add"), {"product": self.set.pk, "quantity": 1}, **headers)
        self.assertFalse(r.json()["ok"])
        self.assertEqual(r.json()["count"], 37)
        # with counts shown the message names the number
        Product.objects.filter(pk=self.part.pk).update(show_stock=True)
        r = self.client.post(reverse("cart:add"), {"product": self.part.pk, "quantity": 2000}, **headers)
        self.assertIn("у наявності лише 1234 шт.", r.json()["message"])

    def test_owner_switches_counts_in_the_panel(self):
        self.client.force_login(self.staff)
        form = self.client.get(reverse("panel:product_edit", args=[self.set.pk])).content.decode()
        self.assertIn('name="show_stock"', form)
        self.client.post(reverse("panel:product_bulk"), {"ids": [self.set.pk], "action": "show_stock"})
        self.set.refresh_from_db()
        self.assertTrue(self.set.show_stock)
        listing = self.client.get(reverse("panel:products")).content.decode()
        self.assertIn("кількість видно", listing)
        self.client.post(reverse("panel:product_bulk"), {"ids": [self.set.pk], "action": "hide_stock"})
        self.set.refresh_from_db()
        self.assertFalse(self.set.show_stock)

    def test_bulk_action_for_everything_the_filter_finds(self):
        self.client.force_login(self.staff)
        other = part_product(design="3001", color=self.colors["black"], qty=5)
        r = self.client.post(reverse("panel:product_bulk"), {"scope": "all", "filters": "kind=part",
                                                             "action": "show_stock"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(set(Product.objects.filter(show_stock=True).values_list("pk", flat=True)),
                         {self.part.pk, other.pk})
        # deleting needs an explicit choice of products
        self.client.post(reverse("panel:product_bulk"), {"scope": "all", "filters": "kind=part", "action": "delete"})
        self.assertEqual(Product.objects.filter(kind="part").count(), 2)
