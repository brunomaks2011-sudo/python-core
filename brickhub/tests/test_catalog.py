from django.core import mail
from django.test import TestCase
from django.urls import reverse

from catalog.models import Inventory, Product, StockNotification
from catalog.search import search_products

from .factories import base_catalog, minifig_product, part_product, set_product


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.red = part_product(color=cls.colors["red"], element="EL-TEST-01")
        cls.black = part_product(color=cls.colors["black"], price="6.50")
        cls.clear = part_product(design="3062b", name="Brick Round 1 x 1 Open Stud", name_uk="Цеглинка кругла 1 × 1",
                                 color=cls.colors["clear"], price="2.50")
        cls.xwing = set_product()
        cls.fig = minifig_product()

    def test_product_identifiers(self):
        self.assertEqual(self.red.sku, "BH-P-3001-5-N")
        self.assertEqual(self.red.official_number, "3001")
        self.assertEqual(self.xwing.official_number, "75355")
        self.assertTrue(self.xwing.slug.startswith("lego-star-wars-75355"))
        self.assertTrue(Inventory.objects.filter(product=self.red).exists())

    def _search(self, q):
        qs, _ = search_products(Product.objects.active(), q)
        return list(qs.order_by("-rank"))

    def test_search_by_numbers_and_colour(self):
        self.assertEqual(self._search("75355")[0], self.xwing)
        self.assertIn(self.red, self._search("3001"))
        self.assertEqual(self._search("3001 червоний"), [self.red])
        self.assertEqual(self._search("3001 black"), [self.black])
        self.assertEqual(self._search("el-test-01"), [self.red])
        self.assertEqual(self._search("fig-000001"), [self.fig])
        self.assertEqual(self._search("x-wing")[0], self.xwing)

    def test_listing_filters(self):
        url = reverse("catalog:category", args=["detali"])
        r = self.client.get(url, {"color": "red"})
        self.assertContains(r, "Цеглинка 2 × 4")
        self.assertNotContains(r, "Цеглинка кругла")
        r = self.client.get(reverse("catalog:collection", args=["prozori-detali"]))
        self.assertContains(r, "Цеглинка кругла 1 × 1")
        r = self.client.get(reverse("catalog:category", args=["nabory"]), {"pieces_min": 5000})
        self.assertNotContains(r, "X-Wing Starfighter")
        r = self.client.get(reverse("catalog:category", args=["nabory"]), {"year_min": 2023, "sort": "price_asc"})
        self.assertContains(r, "X-Wing Starfighter")

    def test_pages_render(self):
        for url in [reverse("core:home"), self.red.get_absolute_url(), self.xwing.get_absolute_url(),
                    self.fig.get_absolute_url(), reverse("catalog:part_design", args=["3001"]),
                    reverse("catalog:part_finder") + "?q=3001", reverse("catalog:search") + "?q=3001",
                    reverse("catalog:colors"), reverse("core:sitemap"), reverse("core:robots")]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_product_page_has_jsonld_and_ids(self):
        r = self.client.get(self.red.get_absolute_url())
        self.assertContains(r, '"@type": "Product"')
        self.assertContains(r, "EL-TEST-01")
        self.assertContains(r, "BH-P-3001-5-N")

    def test_suggest_api(self):
        r = self.client.get(reverse("catalog:suggest"), {"q": "3001"})
        data = r.json()
        self.assertEqual(data["design"]["id"], "3001")
        self.assertGreaterEqual(data["total"], 2)

    def test_part_svg(self):
        r = self.client.get(reverse("catalog:part_svg", args=["3001", self.colors["red"].pk]))
        self.assertEqual(r["Content-Type"], "image/svg+xml")
        self.assertIn("immutable", r["Cache-Control"])

    def test_back_in_stock_email(self):
        Inventory.objects.filter(product=self.black).update(quantity=0)
        StockNotification.objects.create(product=self.black, email="fan@example.com")
        inv = Inventory.objects.get(product=self.black)
        with self.captureOnCommitCallbacks(execute=True):
            inv.quantity = 10
            inv.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("знову в наявності", mail.outbox[0].subject)
        self.assertIsNotNone(StockNotification.objects.get(email="fan@example.com").notified_at)

    def test_favorites_and_compare_for_guest(self):
        r = self.client.post(reverse("catalog:toggle_favorite", args=[self.xwing.pk]), HTTP_X_REQUESTED_WITH="fetch")
        self.assertTrue(r.json()["active"])
        r = self.client.post(reverse("catalog:toggle_compare", args=[self.xwing.pk]), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json()["count"], 1)
        self.assertContains(self.client.get(reverse("catalog:compare")), "X-Wing Starfighter")


class PhotoAndVariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.red = part_product(color=cls.colors["red"])
        cls.black = part_product(color=cls.colors["black"], qty=0)
        cls.red_used = part_product(color=cls.colors["red"], condition="used", price="3.00")
        cls.single = part_product(design="3062b", name="Brick Round 1 x 1 Open Stud", name_uk="Кругла 1 × 1",
                                  color=cls.colors["clear"])
        cls.xwing = set_product()

    def test_only_owner_photos_are_shown(self):
        for product in (self.xwing, self.red):
            html = self.client.get(product.get_absolute_url()).content.decode()
            gallery = html.split('class="gallery-main"', 1)[1].split('class="card-badges"', 1)[0]
            self.assertIn("img/no-photo.svg", gallery)
            self.assertNotIn("/img/part/", gallery)
            self.assertNotIn('"image":', html)  # no picture in JSON-LD without a real photo
        r = self.client.get(reverse("catalog:category", args=["detali"]))
        cards = r.content.decode().split('class="listing"', 1)[1]
        self.assertNotIn("/img/part/", cards.split('class="card-media', 1)[1].split("</a>", 1)[0])
        from catalog.models import ProductImage

        ProductImage.objects.create(product=self.xwing, external_url="https://example.com/my-photo.jpg")
        r = self.client.get(self.xwing.get_absolute_url())
        self.assertContains(r, "https://example.com/my-photo.jpg")

    def test_colour_picker(self):
        r = self.client.get(self.red.get_absolute_url())
        self.assertContains(r, 'class="variant-picker" id="kolir"')
        self.assertContains(r, "data-variant-select")
        self.assertContains(r, self.black.get_absolute_url())
        self.assertContains(r, "немає в наявності")  # black is out of stock
        # condition switch: the red part is also sold used
        self.assertContains(r, self.red_used.get_absolute_url())
        self.assertContains(r, "Б/у")

    def test_no_picker_for_single_colour(self):
        r = self.client.get(self.single.get_absolute_url())
        self.assertNotContains(r, 'id="kolir"')

    def test_clear_auto_images_command(self):
        from django.core.management import call_command

        from catalog.models import ProductImage

        ProductImage.objects.create(product=self.red, external_url="https://cdn.rebrickable.com/media/x.jpg")
        ProductImage.objects.create(product=self.red, external_url="https://example.com/mine.jpg")
        call_command("clear_auto_images", stdout=__import__("io").StringIO())
        self.assertEqual(list(ProductImage.objects.values_list("external_url", flat=True)),
                         ["https://example.com/mine.jpg"])


class AnimalsCategoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()

    def test_category_exists_and_is_listed(self):
        from catalog.models import Category

        animals = Category.objects.get(slug="tvaryny")
        self.assertEqual(animals.parent.slug, "detali")
        self.assertEqual(animals.kind, "part")
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, reverse("catalog:category", args=["tvaryny"]))
        self.assertContains(r, "img/categories/tvaryny.svg")

    def test_migration_moves_catalogue_parts_but_not_products(self):
        import importlib

        from django.apps import apps

        from catalog.models import Category, Part, PartCategory

        migration = importlib.import_module("catalog.migrations.0005_animals_category")
        other = Category.objects.get(slug="inshi-elementy")
        animals = Category.objects.get(slug="tvaryny")
        PartCategory.objects.create(id=28, name="Animals / Creatures")
        horse = Part.objects.create(design_id="horse-test", name="Animal, Horse", part_category_id=28, category=other)
        product = Product.objects.create(kind="part", part=horse, color=self.colors["black"], price="99",
                                         category=other)
        migration.add_animals(apps, None)
        horse.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(horse.category, animals)
        self.assertEqual(product.category, other)  # the owner's listing keeps its category

    def test_part_in_animals_category_is_shown_there(self):
        from catalog.models import Category

        p = part_product(design="3001", color=self.colors["red"])
        p.category = Category.objects.get(slug="tvaryny")
        p.save()
        r = self.client.get(reverse("catalog:category", args=["tvaryny"]))
        self.assertContains(r, "Цеглинка 2 × 4")
