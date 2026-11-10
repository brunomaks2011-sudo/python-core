"""Third level of part categories: minifigure heads / torsos / legs, hair / helmets, Technic types ..."""
import importlib
import re

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.importer import import_parts
from catalog.models import Category, Part, PartCategory, Product
from catalog.structure import PART_CATEGORIES, PART_SUBCATEGORIES, name_rules

from .factories import base_catalog, part_product

migration = importlib.import_module("catalog.migrations.0007_part_subcategories")


class SubcategoryStructureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()

    def test_structure_and_migration_agree(self):
        self.assertEqual(migration.SUBCATEGORIES, PART_SUBCATEGORIES)
        seconds = {row[0]: row for row in PART_CATEGORIES}
        for slug, *_rest in migration.NEW_PART_CATEGORIES:
            self.assertIn(slug, seconds)
        for parent, children in PART_SUBCATEGORIES.items():
            self.assertEqual(seconds[parent][4], "", f"{parent} gives its part types to its subcategories")
            for slug, name, *_ in children:
                cat = Category.objects.get(slug=slug)
                self.assertEqual((cat.parent.slug, cat.kind, cat.name), (parent, "part", name))
        self.assertEqual(Category.objects.get(slug="holovy").ancestors()[0].slug, "detali")
        self.assertEqual(name_rules()[65], [(("hair",), "volossia"), (("helmet",), "sholomy")])

    def test_migration_splits_parts_by_type_and_name_but_keeps_products(self):
        # an install from before migration 0007
        leaves = [row[0] for children in PART_SUBCATEGORIES.values() for row in children]
        Category.objects.filter(slug__in=leaves).delete()
        Category.objects.filter(slug__in=["chastyny-minilialok", "bionicle"]).delete()
        figs = Category.objects.get(slug="chastyny-minifihurok")
        hats = Category.objects.get(slug="volossia-ta-holovni-ubory")
        weapons = Category.objects.get(slug="zbroia-ta-instrumenty")
        bricks = Category.objects.get(slug="tsehlynky")
        for cat, ids in ((figs, "59,60,61,13"), (hats, "65,72"), (weapons, "73")):
            cat.rebrickable_part_categories = ids
            cat.save()
        PartCategory.objects.bulk_create([PartCategory(id=i, name=f"type {i}") for i in (59, 65, 73, 41)])
        head = Part.objects.create(design_id="head-t", name="Minifig Head Smile", part_category_id=59, category=figs)
        hair = Part.objects.create(design_id="hair-t", name="Hair Short Tousled", part_category_id=65, category=hats)
        helmet = Part.objects.create(design_id="helm-t", name="Helmet Classic", part_category_id=65, category=hats)
        hat = Part.objects.create(design_id="hat-t", name="Hat, Cowboy", part_category_id=65)
        mine = Part.objects.create(design_id="hair-m", name="Hair Long", part_category_id=65, category=bricks)
        shield = Part.objects.create(design_id="shld-t", name="Shield Round", part_category_id=73, category=weapons)
        sword = Part.objects.create(design_id="swrd-t", name="Weapon Sword", part_category_id=73, category=weapons)
        mask = Part.objects.create(design_id="bion-t", name="Bionicle Mask", part_category_id=41)
        listing = Product.objects.create(kind="part", part=head, color=self.colors["red"], price="15", category=figs)

        migration.add_subcategories(apps, None)
        migration.add_subcategories(apps, None)  # running it again changes nothing

        def cat_of(part):
            part.refresh_from_db()
            return part.category.slug if part.category_id else None

        self.assertEqual([cat_of(p) for p in (head, hair, helmet, hat, mine, shield, sword, mask)],
                         ["holovy", "volossia", "sholomy", "kapeliukhy-ta-masky", "tsehlynky", "shchyty", "zbroia",
                          "bionicle"])
        listing.refresh_from_db()
        self.assertEqual(listing.category, figs)  # the owner's listing keeps its category
        figs.refresh_from_db()
        self.assertEqual(figs.rebrickable_part_categories, "")
        self.assertEqual(Category.objects.get(slug="kapeliukhy-ta-masky").rebrickable_part_categories, "65")
        self.assertEqual(Category.objects.get(slug="volossia").rebrickable_part_categories, "")
        self.assertEqual(Category.objects.filter(slug="holovy").count(), 1)

    def test_catalogue_import_sorts_parts_into_subcategories(self):
        PartCategory.objects.bulk_create([PartCategory(id=65, name="Minifig Headwear"),
                                          PartCategory(id=60, name="Minifig Upper Body")])
        import_parts([("imp-hair", "Hair Ponytail", 65), ("imp-helm", "Helmet Space", 65), ("imp-cap", "Cap, Short", 65),
                      ("imp-torso", "Torso Police", 60)])
        got = dict(Part.objects.filter(design_id__startswith="imp-").values_list("design_id", "category__slug"))
        self.assertEqual(got, {"imp-hair": "volossia", "imp-helm": "sholomy", "imp-cap": "kapeliukhy-ta-masky",
                               "imp-torso": "torsy"})


class SubcategoryPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.head = part_product(design="3626c", name="Minifig Head", name_uk="Голова мініфігурки",
                                color=cls.colors["red"])
        holovy = Category.objects.get(slug="holovy")
        Part.objects.filter(pk=cls.head.part_id).update(category=holovy)
        Product.objects.filter(pk=cls.head.pk).update(category=holovy)
        cls.staff = User.objects.create_user("cats@example.com", "Correct-horse-1", is_staff=True)

    def test_third_level_page_has_full_crumbs_and_siblings(self):
        html = self.client.get(reverse("catalog:category", args=["holovy"])).content.decode()
        crumbs = re.search(r'<nav class="crumbs".*?</nav>', html, re.S).group(0)
        self.assertLess(crumbs.index("Деталі LEGO"), crumbs.index("Частини мініфігурок"))
        self.assertIn('class="chip is-active" href="/katalog/holovy/"', html)
        self.assertIn('href="/katalog/torsy/"', html)
        self.assertIn("Голова мініфігурки", html)
        # the parent shows the products of its subcategories
        self.assertContains(self.client.get(reverse("catalog:category", args=["chastyny-minifihurok"])),
                            "Голова мініфігурки")
        product_page = self.client.get(self.head.get_absolute_url()).content.decode()
        self.assertIn('href="/katalog/chastyny-minifihurok/"', product_page)

    def test_part_finder_and_home_count_subcategories(self):
        r = self.client.get(reverse("catalog:part_finder") + "?category=chastyny-minifihurok")
        self.assertContains(r, "3626c")
        self.assertContains(r, "— Голови")
        home = self.client.get(reverse("core:home"))
        tile = next(c for c in home.context["part_categories"] if c.slug == "chastyny-minifihurok")
        self.assertEqual(tile.n, 1)

    def test_bulk_files_parts_by_catalogue_category(self):
        self.client.force_login(self.staff)
        other = Category.objects.get(slug="chastyny-minifihurok")
        Product.objects.filter(pk=self.head.pk).update(category=other)
        self.client.post(reverse("panel:product_bulk"), {"ids": [self.head.pk], "action": "category_from_catalog"})
        self.head.refresh_from_db()
        self.assertEqual(self.head.category.slug, "holovy")

    def test_category_picker_is_a_tree_with_full_paths(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("panel:product_new") + "?kind=part").content.decode()
        labels = re.findall(r'<option value="\d+"[^>]*>(Деталі LEGO › Цеглинки[^<]*)</option>', html)
        self.assertEqual(labels[:3], ["Деталі LEGO › Цеглинки", "Деталі LEGO › Цеглинки › Звичайні цеглинки",
                                      "Деталі LEGO › Цеглинки › Модифіковані цеглинки"])
