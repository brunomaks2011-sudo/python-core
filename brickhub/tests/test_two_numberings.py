"""LEGO (Pick a Brick) and BrickLink number parts differently: the shop keeps both, LEGO's first."""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog import item_info
from catalog.importer import fill_lego_numbers
from catalog.models import Category, Element, Part, Product

from .factories import base_catalog, part_product


class TwoNumberingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("numbers2@example.com", "Correct-horse-1", is_staff=True)
        torsy = Category.objects.get(slug="torsy")
        cls.torso_a = Part.objects.create(design_id="973pr0001c01", name="Torso Police", category=torsy,
                                          bricklink_no="973pb0101c01")
        cls.torso_b = Part.objects.create(design_id="973pr0002c01", name="Torso Pirate", category=torsy)
        Element.objects.create(element_id="6000001", part=cls.torso_a, color=cls.colors["red"], lego_design_id="76382")
        Element.objects.create(element_id="6000002", part=cls.torso_b, color=cls.colors["red"], lego_design_id="76382")

    def setUp(self):
        cache.clear()
        cache.set(item_info.OFFLINE_KEY, True)
        self.brick = part_product(design="3005", name="Brick 1 x 1", color=self.colors["red"])
        Element.objects.create(element_id="300521", part=self.brick.part, color=self.colors["red"],
                               lego_design_id="35382")
        Element.objects.create(element_id="300526", part=self.brick.part, color=self.colors["black"],
                               lego_design_id="35382")
        Element.objects.create(element_id="300501", part=self.brick.part, color=self.colors["clear"],
                               lego_design_id="3005")
        self.brick = Product.objects.get(pk=self.brick.pk)

    def test_lego_number_first_then_bricklink(self):
        self.assertEqual(self.brick.lego_design_id, "35382")
        self.assertEqual(self.brick.official_number, "35382")
        self.assertEqual(self.brick.number_label, "Design ID (LEGO)")
        self.assertEqual(self.brick.bricklink_number, "3005")
        html = self.client.get(self.brick.get_absolute_url()).content.decode()
        self.assertIn("Design ID (LEGO)", html)
        self.assertLess(html.index("35382"), html.index("Номер BrickLink"))
        self.assertIn('<td class="mono">3005</td>', html)

    def test_without_lego_data_the_bricklink_number_is_shown(self):
        product = part_product(design="973pr0001c01", color=self.colors["black"])
        product = Product.objects.get(pk=product.pk)
        Part.objects.filter(pk=self.torso_a.pk).update(lego_no="")
        self.assertEqual((product.official_number, product.number_label), ("973pb0101c01", "Номер BrickLink"))

    def test_parts_get_the_lego_number_most_of_their_elements_carry(self):
        self.assertEqual(fill_lego_numbers(), 3)
        self.assertEqual(Part.objects.get(design_id="3005").lego_no, "35382")
        self.assertEqual(Part.objects.get(design_id="973pr0001c01").lego_no, "76382")
        Part.objects.filter(design_id="3005").update(lego_no="mine")
        fill_lego_numbers()
        self.assertEqual(Part.objects.get(design_id="3005").lego_no, "mine")  # one already there stays

    def test_a_shared_lego_number_does_not_pick_a_torso(self):
        fill_lego_numbers()
        self.assertEqual(item_info.known_part("35382"), self.brick.part)
        self.assertIsNone(item_info.known_part("76382"))
        self.assertEqual(item_info.known_part("973pb0101c01"), self.torso_a)

    def test_pick_a_brick_numbers_give_the_exact_part(self):
        """Design ID 76382 + Element ID from lego.com: the element says which torso it is."""
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "part", "condition": "new", "design_id": "76382", "element_id": "6000002", "price": "40",
            "quantity": 1, "is_active": "on", "standalone": "on"})
        self.assertEqual(r.status_code, 302)
        product = Product.objects.get(part=self.torso_b)
        self.assertEqual((product.color, product.lego_design_id), (self.colors["red"], "76382"))
        self.assertFalse(Part.objects.filter(design_id="76382").exists())

    def test_lookup_returns_both_numbers(self):
        self.client.force_login(self.staff)
        d = self.client.get(reverse("panel:catalog_lookup"),
                            {"kind": "part", "q": "6000001", "by": "element"}).json()
        self.assertEqual((d["lego_design_id"], d["bricklink_no"]), ("76382", "973pb0101c01"))
        d = self.client.get(reverse("panel:catalog_lookup"),
                            {"kind": "part", "q": "3005", "color": self.colors["black"].pk}).json()
        self.assertEqual((d["lego_design_id"], d["bricklink_no"], d["element_id"]), ("35382", "3005", "300526"))

    def test_editing_keeps_the_part_and_its_bricklink_number(self):
        self.client.force_login(self.staff)
        form = self.client.get(reverse("panel:product_edit", args=[self.brick.pk])).context["form"]
        self.assertEqual((form["design_id"].value(), form["bricklink_no"].value()), ("35382", "3005"))
        r = self.client.post(reverse("panel:product_edit", args=[self.brick.pk]), {
            "kind": "part", "condition": "new", "design_id": "35382", "bricklink_no": "3005",
            "element_id": "300521", "color": self.colors["red"].pk, "price": "2", "quantity": 5, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.brick.refresh_from_db()
        self.assertEqual(self.brick.part.design_id, "3005")
        self.assertEqual(Part.objects.get(design_id="3005").bricklink_no, "")

    def test_print_numbers_are_not_passed_off_as_bricklink(self):
        """The catalogue writes prints as ...pr0002..., BrickLink as ...pb...: unknown until the owner types it."""
        self.assertFalse(self.torso_b.bricklink_known)
        self.assertEqual(self.torso_b.bricklink_shown, "")
        self.assertEqual(self.torso_a.bricklink_shown, "973pb0101c01")  # typed in: known
        self.client.force_login(self.staff)
        d = self.client.get(reverse("panel:catalog_lookup"),
                            {"kind": "part", "q": "6000002", "by": "element"}).json()
        self.assertEqual((d["lego_design_id"], d["bricklink_no"]), ("76382", ""))
        product = part_product(design="973pr0002c01", color=self.colors["red"])
        html = self.client.get(product.get_absolute_url()).content.decode()
        self.assertNotIn("Номер BrickLink", html)
        self.assertIn("76382", html)
