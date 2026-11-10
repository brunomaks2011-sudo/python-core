"""More part categories, accessory subcategories, and accessory pages without set wording."""
import importlib
import re
from html.parser import HTMLParser

from django.apps import apps
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Inventory, LegoSet, Part, PartCategory, Product, Theme
from catalog.structure import ACCESSORY_CATEGORIES, PART_CATEGORIES
from catalog.templatetags.shop_tags import STATIC_CATEGORY_ICONS

from .factories import base_catalog, part_product

migration = importlib.import_module("catalog.migrations.0006_more_categories")
migration7 = importlib.import_module("catalog.migrations.0007_part_subcategories")

# sort orders of the part categories on installs made before migration 0006
OLD_SORT_ORDERS = {"tsehlynky": 0, "plastyny": 10, "plytky": 20, "kolesa-ta-shyny": 30, "vikna-ta-dveri": 40,
                   "kryla": 50, "shesterni": 60, "elementy-technic": 70, "prozori-detali": 80, "roslyny": 90,
                   "tvaryny": 95, "aksesuary-dlia-fihurok": 100, "inshi-elementy": 110}
SET_WORDS = re.compile(r"набір|набору|набори|наборів|набор", re.IGNORECASE)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _VisibleText(HTMLParser):
    """Text of the product form as a person sees it with one product type chosen."""

    def __init__(self, kind):
        super().__init__(convert_charrefs=True)
        self.kind, self.stack, self.parts = kind, [], []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        section = dict(attrs).get("data-kind-section")
        hidden = (section is not None and self.kind not in section.split()) or tag in ("option", "script", "style")
        self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not any(hidden for _tag, hidden in self.stack):
            self.parts.append(data)


def visible_form_text(html: str, kind: str) -> str:
    start = html.index('<form class="pform"')
    parser = _VisibleText(kind)
    parser.feed(html[start:html.index("</form>", start) + len("</form>")])
    return " ".join(" ".join(parser.parts).split())


class MoreCategoriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()

    def test_new_categories_exist_in_both_sections(self):
        structure_names = {slug: name for slug, name, *_ in PART_CATEGORIES}
        for slug, name, *_ in migration.PART_CATEGORIES:
            self.assertEqual(structure_names.get(slug), name)
            cat = Category.objects.get(slug=slug)
            self.assertEqual((cat.parent.slug, cat.kind), ("detali", "part"))
        self.assertEqual([row[:2] for row in ACCESSORY_CATEGORIES],
                         [row[:2] for row in migration.ACCESSORY_CATEGORIES])
        for slug, *_ in ACCESSORY_CATEGORIES:
            cat = Category.objects.get(slug=slug)
            self.assertEqual((cat.parent.slug, cat.kind), ("aksesuary", "accessory"))
        self.assertEqual(Category.objects.get(slug="aksesuary-dlia-fihurok").name, "Аксесуари для фігурок")

    def test_migrated_and_fresh_installs_list_part_categories_in_the_same_order(self):
        orders = dict(OLD_SORT_ORDERS)
        orders.update({slug: order for slug, _name, _icon, order, *_ in migration.PART_CATEGORIES})
        orders.update({slug: order for slug, _name, _icon, order, *_ in migration7.NEW_PART_CATEGORIES})
        self.assertEqual(sorted(orders, key=orders.get), [slug for slug, *_ in PART_CATEGORIES])

    def test_migration_moves_catalogue_parts_but_not_products(self):
        # an install from before the migration: none of the new categories, slopes still in «Цеглинки»
        new_slugs = [row[0] for row in migration.PART_CATEGORIES + migration.ACCESSORY_CATEGORIES]
        Category.objects.filter(slug__in=new_slugs).delete()
        bricks = Category.objects.get(slug="tsehlynky")
        bricks.rebrickable_part_categories = "11,5,20,3,37,6"
        bricks.description = "Класичні цеглинки, скоси, круглі та модифіковані елементи."
        bricks.save()
        figs = Category.objects.get(slug="aksesuary-dlia-fihurok")
        figs.name = "Аксесуари"
        figs.rebrickable_part_categories = "27,73,65,72,71,70,13,59,60,61"
        figs.save()
        other = Category.objects.get(slug="inshi-elementy")
        other.description = "Мій власний опис"
        other.rebrickable_part_categories = "18,32,23,24,7,30,31,33,34,36,38,39,28,74,75,68,69"
        other.save()
        PartCategory.objects.bulk_create([PartCategory(id=3, name="Bricks Sloped"),
                                          PartCategory(id=59, name="Minifig Heads")])
        slope = Part.objects.create(design_id="slope-test", name="Slope 45° 2 x 2", part_category_id=3,
                                    category=bricks)
        head = Part.objects.create(design_id="head-test", name="Minifig Head", part_category_id=59)
        listing = Product.objects.create(kind="part", part=slope, color=self.colors["red"], price="9",
                                         category=bricks)

        migration.add_categories(apps, None)
        migration.add_categories(apps, None)  # running it again changes nothing

        for obj in (slope, head, listing, bricks, figs, other):
            obj.refresh_from_db()
        self.assertEqual(slope.category.slug, "skosy")
        self.assertEqual(head.category.slug, "chastyny-minifihurok")
        self.assertEqual(listing.category, bricks)  # the shop listing keeps its category
        self.assertEqual(bricks.rebrickable_part_categories, "11,5,20,6")
        self.assertEqual(bricks.description, "Класичні, круглі, клиноподібні та модифіковані цеглинки.")
        self.assertEqual((figs.name, figs.rebrickable_part_categories), ("Аксесуари для фігурок", "27,71,70"))
        self.assertEqual(other.rebrickable_part_categories, "24,33,39,68,69")
        self.assertEqual(other.description, "Мій власний опис")  # an owner's own text is kept
        self.assertEqual(Category.objects.filter(slug="skosy").count(), 1)
        self.assertEqual(Category.objects.get(slug="skosy").parent.slug, "detali")
        self.assertEqual(Category.objects.filter(parent__slug="aksesuary").count(),
                         len(migration.ACCESSORY_CATEGORIES))

    def test_menus_icons_and_accessory_sections(self):
        html = self.client.get(reverse("core:home")).content.decode()
        for slug in ("skosy", "bazovi-plastyny", "chastyny-minifihurok", "elektronika", "duplo", "zberihannia",
                     "vitryny-ta-pidstavky", "inshi-aksesuary"):
            self.assertIn(reverse("catalog:category", args=[slug]), html)
        self.assertIn("img/categories/zberihannia.svg", html)
        self.assertIn("Усі аксесуари", html)
        for path in STATIC_CATEGORY_ICONS.values():
            self.assertTrue(finders.find(path), path)

        storage = Product.objects.create(kind="accessory", title="Контейнер-цеглинка", price="799",
                                         category=Category.objects.get(slug="zberihannia"))
        Inventory.objects.filter(product=storage).update(quantity=2)
        self.assertContains(self.client.get(reverse("catalog:category", args=["zberihannia"])), "Контейнер-цеглинка")
        section = self.client.get(reverse("catalog:category", args=["aksesuary"]))
        self.assertContains(section, "Контейнер-цеглинка")
        self.assertContains(section, "Вітрини та підставки")

    def test_accessory_pages_do_not_talk_about_sets(self):
        theme = Theme.objects.get(slug="star-wars")
        item = LegoSet.objects.create(number="acc-test-1", name="Storage test item", year=2023, pieces=2,
                                      theme=theme, height_cm=10, width_cm=12, depth_cm=18)
        acc = Product.objects.create(kind="accessory", lego_set=item, price="499",
                                     category=Category.objects.get(slug="zberihannia"))
        Inventory.objects.filter(product=acc).update(quantity=3)
        page = self.client.get(acc.get_absolute_url())
        self.assertContains(page, "Розміри (В × Ш × Г)")
        self.assertNotContains(page, "Кількість деталей")
        self.assertNotContains(page, "зібраної моделі")
        listing = self.client.get(reverse("catalog:category", args=["aksesuary"]))
        self.assertContains(listing, "Storage test item")
        self.assertNotContains(listing, "Кількість деталей у наборі")
        self.assertNotContains(listing, " дет.</span>")


class AccessoryFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("staff-acc@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.client.force_login(self.staff)

    def test_nothing_about_sets_when_accessory_is_chosen(self):
        html = self.client.get(reverse("panel:product_new") + "?kind=accessory").content.decode()
        accessory = visible_form_text(html, "accessory")
        self.assertIn("Номер LEGO", accessory)
        self.assertIn("40000803", accessory)
        self.assertIsNone(SET_WORDS.search(accessory), SET_WORDS.findall(accessory))
        self.assertIn("Характеристики набору", visible_form_text(html, "set"))  # the check itself works

    def test_category_picker_knows_category_types(self):
        html = self.client.get(reverse("panel:product_new") + "?kind=accessory").content.decode()
        storage = Category.objects.get(slug="zberihannia")
        self.assertRegex(html, rf'<option value="{storage.pk}"[^>]*data-kind="accessory"[^>]*>'
                               r'Аксесуари › Зберігання та органайзери</option>')

    def test_accessory_saved_into_subcategory(self):
        storage = Category.objects.get(slug="zberihannia")
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "accessory", "condition": "new", "title": "Органайзер для деталей", "category": storage.pk,
            "price": "650", "quantity": 1, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Product.objects.get(title="Органайзер для деталей").category, storage)

    def test_bulk_move_to_category(self):
        a = part_product(design="3001", color=self.colors["red"])
        b = part_product(design="3001", color=self.colors["black"])
        slopes = Category.objects.get(slug="skosy")
        r = self.client.post(reverse("panel:product_bulk"), {"ids": [a.pk, b.pk], "action": "set_category",
                                                              "category": slopes.pk})
        self.assertEqual(r.status_code, 302)
        for p in (a, b):
            p.refresh_from_db()
            self.assertEqual(p.category, slopes)
            self.assertIn("скоси", p.search_text)
        # without a chosen category nothing changes
        self.client.post(reverse("panel:product_bulk"), {"ids": [a.pk], "action": "set_category", "category": ""})
        a.refresh_from_db()
        self.assertEqual(a.category, slopes)
        page = self.client.get(reverse("panel:products"))
        self.assertContains(page, 'value="set_category"')
        self.assertContains(page, '<optgroup label="Аксесуари">')
        self.assertContains(self.client.get(reverse("panel:products") + "?category=skosy"), a.sku)
