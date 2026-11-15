"""A number never becomes a product's name: new sets get theirs from the catalogue, BrickLink or the owner."""
import gzip
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog import item_info
from catalog.models import LegoSet, Minifigure, Product, Theme

from .factories import base_catalog


class FakeResponse:
    def __init__(self, text):
        self.text = text.encode()

    def read(self, n=-1):
        return self.text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class NewSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("sets@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        cache.clear()
        cache.set(item_info.OFFLINE_KEY, True)  # BrickLink out of reach unless a test says otherwise
        self.client.force_login(self.staff)

    def post_set(self, number, title=""):
        return self.client.post(reverse("panel:product_new"), {
            "kind": "set", "condition": "new", "set_number": number, "title": title, "price": "2999",
            "quantity": 1, "is_active": "on"})

    def test_new_set_without_a_name_asks_for_one(self):
        r = self.post_set("77001")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Впишіть його назву", r.content.decode())
        self.assertFalse(LegoSet.objects.filter(number="77001-1").exists())
        d = self.client.get(reverse("panel:catalog_lookup"), {"kind": "set", "q": "77001"}).json()
        self.assertFalse(d["found"])
        self.assertIn("впишіть його назву", d["message"])

    def test_new_set_takes_the_typed_name(self):
        r = self.post_set("77001", title="Castle of the Lions")
        self.assertEqual(r.status_code, 302)
        product = Product.objects.get(lego_set__number="77001-1")
        self.assertEqual(product.title, "Castle of the Lions")
        self.assertEqual(product.lego_set.name, "Castle of the Lions")

    def test_new_set_takes_bricklink_name(self):
        cache.delete(item_info.OFFLINE_KEY)
        page = ("<title>BrickLink - Set 77002-1 : LEGO Dragon Tower [Castle] - BrickLink Reference Catalog</title>")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(page)):
            d = self.client.get(reverse("panel:catalog_lookup"), {"kind": "set", "q": "77002"}).json()
            r = self.post_set("77002")
        self.assertEqual((d["found"], d["name"]), (True, "Dragon Tower"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Product.objects.get(lego_set__number="77002-1").title, "Dragon Tower")

    def test_new_minifigure_without_a_name_asks_for_one(self):
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "minifig", "condition": "new", "fig_number": "abc123", "price": "150", "quantity": 1,
            "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Впишіть її в поле «Назва»", r.content.decode())
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "minifig", "condition": "new", "fig_number": "abc123", "title": "Knight with Shield",
            "price": "150", "quantity": 1, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Minifigure.objects.get(fig_number="abc123").name, "Knight with Shield")
        self.assertFalse(Product.objects.filter(title="abc123").exists())

    def test_update_catalog_adds_new_sets_and_series(self):
        folder = Path(tempfile.mkdtemp())
        with gzip.open(folder / "themes.csv.gz", "wt", encoding="utf-8") as fh:
            fh.write("id,name,parent_id\n158,Star Wars,\n900,Brand New Series,158\n")
        with gzip.open(folder / "sets.csv.gz", "wt", encoding="utf-8") as fh:
            fh.write("set_num,name,year,theme_id,num_parts\n77003-1,Starfighter 2026,2026,900,812\n")
        out = StringIO()
        call_command("update_catalog", "--dir", str(folder), stdout=out)
        self.assertIn("Набори: додано 1", out.getvalue())
        s = LegoSet.objects.get(number="77003-1")
        self.assertEqual((s.name, s.year, s.pieces, s.theme.name), ("Starfighter 2026", 2026, 812, "Brand New Series"))
        self.assertEqual(Theme.objects.get(rebrickable_id=900).parent.rebrickable_id, 158)
        self.assertEqual(Theme.objects.get(rebrickable_id=158).name, "Star Wars")  # existing series untouched
        r = self.post_set("77003")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Product.objects.get(lego_set=s).title, "Starfighter 2026")
