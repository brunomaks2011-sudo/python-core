"""Products are kept in an Excel table: from the panel, by command, and always before clear_products deletes them."""
import io
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from accounts.models import User
from catalog.models import Element, Product

from .factories import base_catalog, part_product, set_product


class ExcelExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("excel@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.brick = part_product(design="3005", name="Brick 1 x 1", color=self.colors["red"], qty=120, price="2.50")
        Element.objects.create(element_id="300521", part=self.brick.part, color=self.colors["red"],
                               lego_design_id="35382")
        self.set = set_product(qty=2, price="8999")
        self.dir = Path(tempfile.mkdtemp())

    def rows(self, data):
        ws = load_workbook(io.BytesIO(data) if isinstance(data, bytes) else data)["Товари"]
        header = [c.value for c in ws[1]]
        return [dict(zip(header, [c.value for c in row])) for row in ws.iter_rows(min_row=2)]

    def test_table_has_name_numbers_colour_quantity_and_price(self):
        out = StringIO()
        call_command("export_products", "--out", str(self.dir / "t.xlsx"), stdout=out)
        rows = {r["Артикул"]: r for r in self.rows(self.dir / "t.xlsx")}
        brick = rows[self.brick.sku]
        self.assertEqual((brick["Design ID (LEGO)"], brick["Element ID (LEGO)"], brick["Номер BrickLink"]),
                         ("35382", "300521", "3005"))
        self.assertEqual((brick["Кількість"], float(brick["Ціна, ₴"])), (120, 2.5))
        self.assertIn("Червоний", brick["Колір"])
        self.assertEqual(rows[self.set.sku]["Номер набору / фігурки"], "75355")
        self.assertIn("Збережено товарів: 2", out.getvalue())

    def test_clear_products_saves_the_table_first(self):
        with mock.patch("panel.excel_export.EXPORT_DIR", self.dir):
            out = StringIO()
            call_command("clear_products", "--yes", stdout=out)
        files = list(self.dir.glob("tovary-*.xlsx"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(self.rows(files[0])), 2)
        self.assertFalse(Product.objects.exists())
        self.assertIn("Таблицю з 2 товарами збережено", out.getvalue())

    def test_nothing_is_deleted_when_the_table_cannot_be_saved(self):
        with mock.patch("catalog.management.commands.clear_products.save_products_workbook",
                        side_effect=OSError("disk full")):
            with self.assertRaises(CommandError):
                call_command("clear_products", "--yes", stdout=StringIO())
        self.assertEqual(Product.objects.count(), 2)

    def test_panel_download(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("panel:export_products_xlsx"), {"kind": "part"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertEqual([row["Артикул"] for row in self.rows(r.content)], [self.brick.sku])
        self.client.logout()
        self.assertEqual(self.client.get(reverse("panel:export_products_xlsx")).status_code, 302)
