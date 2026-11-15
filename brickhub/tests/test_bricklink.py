"""BrickLink numbers, pictures, the check page and removing uploaded photos."""
import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog import bricklink as bl
from catalog.models import Element, ProductImage

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
