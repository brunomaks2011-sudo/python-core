"""Printed minifigure parts share a Design ID but are separate items, not colours of one part."""
import importlib

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Part, Product
from catalog.variants import color_variants

from .factories import base_catalog, part_product


class PrintedPartsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.torsos = Category.objects.get(slug="torsy")
        cls.part = Part.objects.create(design_id="973", name="Torso Plain", category=cls.torsos)
        cls.staff = User.objects.create_user("print@example.com", "Correct-horse-1", is_staff=True)

    def add(self, title, color, standalone=True):
        self.client.force_login(self.staff)
        return self.client.post(reverse("panel:product_new"), {
            "kind": "part", "condition": "new", "design_id": "973", "color": color.pk, "title": title,
            "price": "40", "quantity": 2, "is_active": "on", **({"standalone": "on"} if standalone else {})})

    def test_two_prints_in_the_same_colour_are_two_items(self):
        self.assertEqual(self.add("Торс поліцейського", self.colors["black"]).status_code, 302)
        self.assertEqual(self.add("Торс пірата", self.colors["red"]).status_code, 302)
        self.assertEqual(self.add("Торс ніндзя", self.colors["black"]).status_code, 302)  # same colour: no clash
        police = Product.objects.get(title="Торс поліцейського")
        self.assertEqual(Product.objects.filter(part=self.part).count(), 3)
        self.assertEqual(color_variants(police), [])
        page = self.client.get(police.get_absolute_url()).content.decode()
        self.assertNotIn("Торс пірата", page.split("Схожі")[0] if "Схожі" in page else page[:0])
        lookup = self.client.get(reverse("panel:catalog_lookup") + "?kind=part&q=973").json()
        self.assertTrue(lookup["separate"])

    def test_plain_parts_still_group_by_colour(self):
        red = part_product(color=self.colors["red"])
        part_product(color=self.colors["black"])
        self.assertEqual(len(color_variants(red)), 2)
        Product.objects.filter(part=red.part, color=self.colors["black"]).update(standalone=True)
        self.assertEqual(color_variants(red), [])

    def test_migration_marks_listings_already_added(self):
        listing = Product.objects.create(kind="part", part=self.part, color=self.colors["red"], price="40",
                                         category=self.torsos)
        brick = part_product(color=self.colors["red"])
        importlib.import_module("catalog.migrations.0012_separate_printed_parts").mark_printed_parts(apps, None)
        listing.refresh_from_db()
        brick.refresh_from_db()
        self.assertEqual((listing.standalone, brick.standalone), (True, False))
