"""manage.py update_catalog only adds what the shop does not know yet."""
import gzip
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Element, Minifigure, Part

from .factories import base_catalog, part_product


class UpdateCatalogTests(TestCase):
    def setUp(self):
        self.colors = base_catalog()
        self.product = part_product(design="3001", name="Brick 2 x 4", color=self.colors["red"])
        Part.objects.filter(design_id="3001").update(name="Моя назва")  # a name the owner corrected
        Element.objects.create(element_id="300121", part=Part.objects.get(design_id="3001"), color=self.colors["red"])
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "parts.csv").write_text(
            "part_num,name,part_cat_id,part_material\n3001,Brick 2 x 4,11,Plastic\n3002,Brick 2 x 3,11,Plastic\n",
            encoding="utf-8")
        with gzip.open(self.dir / "elements.csv.gz", "wt", encoding="utf-8") as fh:
            fh.write("element_id,part_num,color_id,design_id\n"
                     "300121,3001,4,3001\n"     # already there
                     "300126,3001,0,3001\n"     # new: black
                     "300221,3002,4,3002\n"     # new part from parts.csv
                     "999999,nosuchpart,4,\n")  # unknown part: skipped
        (self.dir / "minifigs.csv").write_text("fig_num,name,num_parts,img_url\nfig-999999,Test Figure,4,\n",
                                               encoding="utf-8")

    def run_command(self, *args):
        out = StringIO()
        call_command("update_catalog", "--dir", str(self.dir), *args, stdout=out)
        return out.getvalue()

    def test_adds_only_missing_rows(self):
        out = self.run_command()
        self.assertIn("Element ID: додано 2, вже були 1", out)
        self.assertIn("Деталі: додано 1, вже були 1", out)
        self.assertEqual(Part.objects.get(design_id="3001").name, "Моя назва")
        self.assertEqual(Part.objects.get(design_id="3002").name, "Brick 2 x 3")
        self.assertEqual(set(Element.objects.values_list("element_id", flat=True)), {"300121", "300126", "300221"})
        self.assertEqual(Element.objects.get(element_id="300126").color, self.colors["black"])
        self.assertTrue(Minifigure.objects.filter(fig_number="fig-999999").exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.part.name, "Моя назва")
        self.assertIn("Довідник оновлено", self.run_command())  # second run adds nothing and does not fail
        self.assertEqual(Element.objects.count(), 3)

    def test_new_part_gets_its_shop_section(self):
        self.run_command()
        part = Part.objects.get(design_id="3002")
        self.assertIsNotNone(part.category)
        self.assertIsInstance(part.category, Category)

    def test_dry_run_writes_nothing(self):
        out = self.run_command("--dry-run")
        self.assertIn("Пробний запуск", out)
        self.assertFalse(Part.objects.filter(design_id="3002").exists())
        self.assertEqual(Element.objects.count(), 1)
