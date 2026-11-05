from decimal import Decimal

from django.test import SimpleTestCase

from catalog.part_art import classify, render_part_svg
from core.utils import format_uah, make_slug, normalize_phone, plural_uk, transliterate


class UtilsTests(SimpleTestCase):
    def test_format_uah(self):
        self.assertEqual(format_uah(1299), "1 299 ₴")
        self.assertEqual(format_uah(Decimal("2.5")), "2,50 ₴")
        self.assertEqual(format_uah(0), "0 ₴")

    def test_plural(self):
        self.assertEqual(plural_uk(1, "деталь", "деталі", "деталей"), "деталь")
        self.assertEqual(plural_uk(3, "деталь", "деталі", "деталей"), "деталі")
        self.assertEqual(plural_uk(11, "деталь", "деталі", "деталей"), "деталей")
        self.assertEqual(plural_uk(22, "деталь", "деталі", "деталей"), "деталі")

    def test_phone(self):
        self.assertEqual(normalize_phone("067 123 45 67"), "+380671234567")
        self.assertEqual(normalize_phone("+38 (050) 111-22-33"), "+380501112233")
        self.assertEqual(normalize_phone("12345"), "")

    def test_slug_translit(self):
        self.assertEqual(transliterate("Цеглинка Їжак"), "Tsehlynka Yizhak")
        self.assertEqual(make_slug("Цеглинка 2 × 4"), "tsehlynka-2-x-4")


class PartArtTests(SimpleTestCase):
    def test_classify_by_name(self):
        self.assertEqual(classify("3001", "Brick 2 x 4")[0], "block")
        self.assertEqual(classify("x1", "Technic Beam 1 x 9 Thick")[0], "beam")
        self.assertEqual(classify("x2", "Technic Gear 24 Tooth")[0], "gear")
        self.assertEqual(classify("x3", "Technic Axle 6")[0], "axle")

    def test_render_is_svg_with_studs(self):
        svg = render_part_svg("3001", "Brick 2 x 4", "C91A09")
        self.assertTrue(svg.startswith("<svg"))
        # 8 studs -> 16 ellipses (bottom + top of each stud)
        self.assertEqual(svg.count("<ellipse"), 16)
