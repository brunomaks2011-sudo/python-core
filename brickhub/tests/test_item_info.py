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


class CatalogueNumbersTests(TestCase):
    """Any number the owner knows finds the part: catalogue number, LEGO design number or Element ID."""

    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        torsy = Category.objects.get(slug="torsy")
        for num in ("973c01h01", "973pr0001c01", "973c02h02", "973pr0002c01"):
            Part.objects.create(design_id=num, name=f"Torso {num}", category=torsy)
        cls.brick = Part.objects.create(design_id="3005", name="Brick 1 x 1",
                                        category=Category.objects.get(slug="zvychaini-tsehlynky"))
        from catalog.models import Element

        Element.objects.create(element_id="300521", part=cls.brick, color=cls.colors["red"], lego_design_id="35382")
        Element.objects.create(element_id="300526", part=cls.brick, color=cls.colors["black"], lego_design_id="35382")
        Element.objects.create(element_id="6000001", part=Part.objects.get(design_id="973pr0001c01"),
                               color=cls.colors["red"], lego_design_id="76382")
        Element.objects.create(element_id="6000002", part=Part.objects.get(design_id="973pr0002c01"),
                               color=cls.colors["red"], lego_design_id="76382")
        cls.staff = User.objects.create_user("numbers@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        cache.clear()
        cache.set(item_info.OFFLINE_KEY, True)  # BrickLink is out of reach in these tests

    def test_lego_design_number_finds_the_part(self):
        self.assertEqual(item_info.known_part("35382"), self.brick)
        self.assertIsNone(item_info.known_part("76382"))  # one torso design, many printed torsos
        info = item_info.new_part_info("76382")
        self.assertEqual((info["source"], info["category"].slug), ("design", "torsy"))

    def test_section_from_numbers_that_start_the_same_way(self):
        info = item_info.new_part_info("973pb2345c01")  # no plain 973 in this catalogue
        self.assertEqual((info["source"], info["category"].slug), ("base", "torsy"))
        self.assertIsNone(item_info.new_part_info("76399")["category"])  # a plain number is not 763 + something

    def test_lookup_fills_the_element_id_for_the_colour(self):
        self.client.force_login(self.staff)
        url = reverse("panel:catalog_lookup")
        d = self.client.get(url, {"kind": "part", "q": "35382", "color": self.colors["black"].pk}).json()
        self.assertEqual((d["design_id"], d["element_id"]), ("3005", "300526"))
        d = self.client.get(url, {"kind": "part", "q": "300521", "by": "element"}).json()
        self.assertEqual((d["design_id"], d["color_id"], d["element_id"]), ("3005", self.colors["red"].pk, "300521"))

    def test_product_from_an_element_id_alone(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "part", "condition": "new", "design_id": "", "element_id": "300526", "price": "3",
            "quantity": 10, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        product = Product.objects.get(part=self.brick)
        self.assertEqual((product.color, product.element_id), (self.colors["black"], "300526"))


class ElementLookupTests(TestCase):
    """An Element ID typed in the panel brings its own colour; an unknown one leaves the form alone."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from catalog.models import Color, Element, Part
        from .factories import base_catalog
        cls.colors = base_catalog()
        cls.nougat = Color.objects.create(name="Medium Nougat", name_uk="Середня нуга", slug="medium-nougat",
                                          rgb="AA7D55", bricklink_id=150, rebrickable_id=84)
        part = Part.objects.create(design_id="30150", name="Box / Crate with Handholds")
        Element.objects.create(element_id="6035734", part=part, color=cls.nougat)
        cls.staff = User.objects.create_user("el@example.com", "Correct-horse-1", is_staff=True)

    def ask(self, **params):
        from django.urls import reverse
        self.client.force_login(self.staff)
        return self.client.get(reverse("panel:catalog_lookup"), params).json()

    def test_element_gives_its_colour_even_with_another_colour_chosen(self):
        d = self.ask(kind="part", q="6035734", by="element", color=self.colors["red"].pk)
        self.assertEqual((d["design_id"], d["color_id"]), ("30150", self.nougat.pk))

    def test_unknown_element_is_not_taken_for_a_design(self):
        d = self.ask(kind="part", q="9999999", by="element")
        self.assertFalse(d["found"])

    def test_owner_can_move_an_element_to_the_right_colour(self):
        from django.urls import reverse
        from catalog.models import Element, Product
        Element.objects.filter(element_id="6035734").update(color=self.colors["red"])  # wrong colour in the catalogue
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "part", "condition": "new", "design_id": "30150", "element_id": "6035734",
            "color": self.nougat.pk, "price": "5", "quantity": "1", "availability": "in_stock", "is_active": "on"})
        self.assertNotContains(r, "вже належить", status_code=r.status_code)
        self.assertEqual(Element.objects.get(element_id="6035734").color_id, self.nougat.pk)
        self.assertTrue(Product.objects.filter(part__design_id="30150", color=self.nougat).exists())
