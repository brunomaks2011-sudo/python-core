"""Home page series: the ones with the most products first; DC joins once it has products, with Batman."""
import re

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from .factories import base_catalog, set_product


class HomeSeriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()

    def order(self):
        html = self.client.get(reverse("core:home")).content.decode()
        return re.findall(r'data-series="([^"]+)"', html)

    def test_most_products_first(self):
        set_product(number="60001-1", name="City one", theme_slug="city")
        for i in range(2):
            set_product(number=f"7500{i}-1", name=f"Star Wars {i}", theme_slug="star-wars")
        order = self.order()
        self.assertEqual(order[:2], ["star-wars", "city"])
        self.assertLessEqual(len(order), 14)  # two rows of seven at most

    def test_dc_joins_once_it_has_products(self):
        self.assertNotIn("dc", self.order())  # not a main series and nothing on sale: no tile
        for i in range(3):
            set_product(number=f"7610{i}-1", name=f"Batman {i}", theme_slug="dc")
        order = self.order()
        self.assertEqual(order[0], "dc")
        self.assertNotIn("jurassic-world", order)  # other extra series still wait for their first product

    def test_brickheadz_joins_once_it_has_products(self):
        from catalog.models import Theme
        Theme.objects.create(name="BrickHeadz", slug="brickheadz", rebrickable_id=610)
        self.assertNotIn("brickheadz", self.order())
        set_product(number="40859-1", name="Superman and Batman", theme_slug="brickheadz")
        self.assertIn("brickheadz", self.order())

    def test_character_pictures_are_in_the_static_files(self):
        for name in ("dc-batman", "brickheadz-emmet", "star-wars-vader"):
            self.assertTrue(finders.find(f"img/series/{name}.webp"), name)
