"""BrickLink numbers, pictures, the check page and removing uploaded photos."""
import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog import bricklink as bl
from catalog.models import Element, Product, ProductImage

from .factories import base_catalog, minifig_product, part_product, set_product


class BrickLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.red = part_product(color=cls.colors["red"], element="300121")
        cls.xwing = set_product()
        cls.fig = minifig_product()
        cls.staff = User.objects.create_user("bl@example.com", "Correct-horse-1", is_staff=True)

    def test_picture_and_catalogue_urls(self):
        self.assertEqual(bl.item_image(self.red), "https://img.bricklink.com/ItemImage/PN/5/3001.png")
        self.assertEqual(bl.catalog_url(self.red), "https://www.bricklink.com/v2/catalog/catalogitem.page?P=3001&idColor=5")
        self.assertEqual(bl.item_image(self.xwing), "https://img.bricklink.com/ItemImage/SN/0/75355-1.png")
        self.assertEqual(bl.item_image(self.fig), "")  # no BrickLink number yet
        self.red.part.bricklink_no = "3001old"
        self.assertEqual(bl.item_image(self.red), "https://img.bricklink.com/ItemImage/PN/5/3001old.png")

    def test_check_page_and_fixing_numbers(self):
        self.client.force_login(self.staff)
        page = self.client.get(reverse("panel:bricklink")).content.decode()
        self.assertIn("https://img.bricklink.com/ItemImage/PN/5/3001.png", page)
        self.assertIn('value="300121"', page)
        r = self.client.post(reverse("panel:bricklink_fix", args=[self.red.pk]),
                             {"bricklink_no": "3001b", "element_id": "300199"})
        self.assertEqual(r.json()["image"], "https://img.bricklink.com/ItemImage/PN/5/3001b.png")
        self.red.part.refresh_from_db()
        self.assertEqual(self.red.part.bricklink_no, "3001b")
        self.assertEqual(list(Element.objects.filter(part=self.red.part).values_list("element_id", flat=True)),
                         ["300199"])
        self.red.refresh_from_db()
        self.assertIn("3001b", self.red.search_text)
        # the Design ID itself is not stored twice
        self.client.post(reverse("panel:bricklink_fix", args=[self.red.pk]), {"bricklink_no": "3001", "element_id": "300199"})
        self.red.part.refresh_from_db()
        self.assertEqual(self.red.part.bricklink_no, "")
        r = self.client.post(reverse("panel:bricklink_fix", args=[self.fig.pk]), {"bricklink_id": "col001"})
        self.assertEqual(r.json()["image"], "https://img.bricklink.com/ItemImage/MN/0/col001.png")
        self.assertContains(self.client.get(reverse("panel:bricklink") + "?tab=sets"), "75355-1")

    def test_removing_uploaded_photos(self):
        ProductImage.objects.create(product=self.xwing, external_url="https://example.com/a.jpg")
        out = io.StringIO()
        call_command("remove_uploaded_photos", stdout=out)
        self.assertIn("Буде видалено фото: 1", out.getvalue())
        self.assertEqual(ProductImage.objects.count(), 1)  # without --yes nothing changes
        call_command("remove_uploaded_photos", "--yes", stdout=out)
        self.assertEqual(ProductImage.objects.count(), 0)


class FillFromRebrickableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.torso = part_product(design="973pr1234c01", name="Torso Police", color=cls.colors["black"])
        cls.brick = part_product(color=cls.colors["red"])

    def fake(self, url, key):
        self.assertEqual(key, "test-key")
        answers = {
            "https://rebrickable.com/api/v3/lego/parts/973pr1234c01/": {"external_ids": {"BrickLink": ["973pb987c01"]}},
            "https://rebrickable.com/api/v3/lego/parts/973pr1234c01/colors/0/": {"elements": ["6123456"]},
            "https://rebrickable.com/api/v3/lego/parts/3001/": {"external_ids": {"BrickLink": ["3001"]}},
            "https://rebrickable.com/api/v3/lego/parts/3001/colors/4/": {"elements": ["300121", "4114309"]},
        }
        if url not in answers:
            from catalog.management.commands.fill_from_rebrickable import NotFound
            raise NotFound(url)
        return answers[url]

    def run_command(self, *args):
        from unittest import mock

        out = io.StringIO()
        with mock.patch("catalog.management.commands.fill_from_rebrickable.get_json", side_effect=self.fake), \
                mock.patch("catalog.management.commands.fill_from_rebrickable.PAUSE", 0):
            call_command("fill_from_rebrickable", "--key", "test-key", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        out = self.run_command("--dry-run")
        self.assertIn("Буде додано: номерів BrickLink 1, Element ID 3", out)
        self.assertEqual(Element.objects.count(), 0)

    def test_fills_bricklink_numbers_and_elements(self):
        self.run_command()
        self.torso.part.refresh_from_db()
        self.assertEqual(self.torso.part.bricklink_no, "973pb987c01")
        self.assertEqual(bl.item_image(Product.objects.get(pk=self.torso.pk)),
                         "https://img.bricklink.com/ItemImage/PN/11/973pb987c01.png")
        self.assertEqual(Product.objects.get(pk=self.brick.pk).element_id, "4114309")  # the newest element
        # picture chain: BrickLink, then the LEGO element photo, then the placeholder
        from catalog.media import image_urls

        src, fallbacks = image_urls(Product.objects.with_related().get(pk=self.brick.pk))
        self.assertEqual(src, "https://img.bricklink.com/ItemImage/PN/5/3001.png")
        self.assertTrue(fallbacks.startswith("https://www.lego.com/cdn/product-assets/element.img.lod5photo.192_192/4114309.jpg "))
        self.assertTrue(fallbacks.endswith("img/no-photo.svg"))
        # a second run only re-checks the BrickLink number of 3001 (it equals the Design ID, so nothing is stored)
        out = self.run_command()
        self.assertIn("Element ID 0", out)
        self.assertIn("Запитів: 1", out)
