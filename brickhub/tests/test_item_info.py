"""A number typed in the panel that the catalogue does not know gets its name and section automatically."""
import urllib.error
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog import item_info
from catalog.models import Category, Minifigure, Part, Product

from .factories import base_catalog

PAGE = ("<html><head><title>BrickLink - Part 973pb2345c01 : LEGO Torso Police Badge and Radio Print / "
        "Black Arms / Yellow Hands [Minifigure, Torso Assembly] - BrickLink Reference Catalog</title></head></html>")


class FakeResponse:
    def __init__(self, text):
        self.text = text.encode()

    def read(self, n=-1):
        return self.text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ItemInfoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        Part.objects.create(design_id="973", name="Torso Plain", category=Category.objects.get(slug="torsy"))
        cls.staff = User.objects.create_user("info@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        cache.clear()

    def test_name_and_section_from_bricklink(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(PAGE)):
            info = item_info.new_part_info("973pb2345c01")
        self.assertEqual(info["source"], "bricklink")
        self.assertEqual(info["name"], "Torso Police Badge and Radio Print / Black Arms / Yellow Hands")
        self.assertEqual(info["category"].slug, "torsy")

    def test_base_part_when_bricklink_is_out_of_reach(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("blocked")) as opened:
            info = item_info.new_part_info("973pb2345c01")
            item_info.new_part_info("973pb7777c01")
        self.assertEqual((info["source"], info["category"].slug), ("base", "torsy"))
        self.assertIn("973pb2345c01", info["name"])
        self.assertEqual(opened.call_count, 1)  # after one failure the server stops trying for a while

    def test_unknown_number_is_saved_with_its_section(self):
        self.client.force_login(self.staff)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("blocked")):
            lookup = self.client.get(reverse("panel:catalog_lookup") + "?kind=part&q=973pb2345c01").json()
            self.assertTrue(lookup["found"] and lookup["new"])
            self.assertEqual(lookup["category_id"], Category.objects.get(slug="torsy").pk)
            r = self.client.post(reverse("panel:product_new"), {
                "kind": "part", "condition": "new", "design_id": "973pb2345c01", "color": self.colors["black"].pk,
                "price": "45", "quantity": 1, "is_active": "on", "standalone": "on"})
        self.assertEqual(r.status_code, 302)
        product = Product.objects.get(part__design_id="973pb2345c01")
        self.assertEqual(product.category.slug, "torsy")
        self.assertEqual(product.part.category.slug, "torsy")
        from catalog.bricklink import item_image

        self.assertEqual(item_image(product), "https://img.bricklink.com/ItemImage/PN/11/973pb2345c01.png")

    def test_unknown_minifigure_number(self):
        page = ("<title>BrickLink - Minifig sw0001a : Battle Droid with One Straight Arm [Star Wars:Star Wars "
                "Episode 1] - BrickLink Reference Catalog</title>")
        self.client.force_login(self.staff)
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(page)):
            r = self.client.post(reverse("panel:product_new"), {
                "kind": "minifig", "condition": "new", "fig_number": "sw0001a", "price": "150", "quantity": 1,
                "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        fig = Minifigure.objects.get(fig_number="sw0001a")
        self.assertEqual((fig.name, fig.bricklink_id), ("Battle Droid with One Straight Arm", "sw0001a"))
        self.assertEqual(fig.theme.slug, "star-wars")

    def test_bulk_import_adds_new_numbers_when_allowed(self):
        from panel.importers import run_import

        rows = [{"design_id": "973pb2345c01", "color": "Black", "price": "45", "quantity": "2"}]
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("blocked")):
            refused = run_import(rows, "parts", dry_run=False, user=self.staff)
            self.assertFalse(Part.objects.filter(design_id="973pb2345c01").exists())
            run_import(rows, "parts", dry_run=False, user=self.staff, allow_new_catalog=True)
        self.assertTrue(any("немає в каталозі" in str(r.message) for r in refused.rows))
        part = Part.objects.get(design_id="973pb2345c01")
        self.assertEqual(part.category.slug, "torsy")
        self.assertTrue(Product.objects.filter(part=part).exists())
