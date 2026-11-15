"""The panel says "без фото" only when the site shows no picture at all (no own photo, no BrickLink / LEGO one)."""
import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Product, ProductImage

from .factories import base_catalog, part_product


class PhotoStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("photos@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.client.force_login(self.staff)
        self.part = part_product(design="3001", color=self.colors["red"])
        self.other = part_product(design="3002", name="Brick 2 x 3", color=self.colors["red"])

    def products_page(self, **params):
        return self.client.get(reverse("panel:products"), params).content.decode()

    def test_unchecked_product_is_checked_in_the_browser(self):
        html = self.products_page()
        self.assertIn(f'data-photo-check="{self.part.pk}"', html)
        self.assertIn("https://img.bricklink.com/ItemImage/PN/5/3001.png", html)
        self.assertIn("data-photo-scan=", html)
        self.assertNotIn("без фото — додайте</span>", html)

    def test_report_is_stored_and_shown(self):
        r = self.client.post(reverse("panel:picture_report"),
                             json.dumps({"results": {str(self.part.pk): "bricklink", str(self.other.pk): "none",
                                                     "x": "bricklink", "999": "fake"}}),
                             content_type="application/json")
        self.assertEqual(r.json()["none"], 1)
        self.part.refresh_from_db()
        self.assertEqual(self.part.catalog_picture, "bricklink")
        html = self.products_page()
        self.assertIn("фото з BrickLink", html)
        self.assertIn("без фото — додайте", html)
        self.assertNotIn("data-photo-scan=", html)  # nothing left to check
        listed = self.client.get(reverse("panel:products"), {"photo": "none"}).context["page"].object_list
        self.assertEqual([p.pk for p in listed], [self.other.pk])
        listed = self.client.get(reverse("panel:products"), {"photo": "has"}).context["page"].object_list
        self.assertEqual([p.pk for p in listed], [self.part.pk])

    def test_own_photo_needs_no_check(self):
        ProductImage.objects.create(product=self.part, external_url="https://example.com/a.jpg")
        queue = self.client.get(reverse("panel:picture_queue")).json()
        self.assertEqual([i["id"] for i in queue["items"]], [self.other.pk])
        self.assertEqual(queue["items"][0]["pictures"][0], "https://img.bricklink.com/ItemImage/PN/5/3002.png")
        self.assertNotIn(f'data-photo-check="{self.part.pk}"', self.products_page())

    def test_editing_the_product_checks_the_picture_again(self):
        Product.objects.filter(pk=self.part.pk).update(catalog_picture="none")
        r = self.client.post(reverse("panel:product_edit", args=[self.part.pk]), {
            "kind": "part", "condition": "new", "design_id": "3001", "color": self.colors["black"].pk,
            "price": "6", "quantity": 100, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.part.refresh_from_db()
        self.assertEqual(self.part.catalog_picture, "")

    def test_recheck_clears_the_none_marks(self):
        Product.objects.filter(pk=self.part.pk).update(catalog_picture="none")
        self.assertIn("Перевірити ще раз", self.products_page(photo="none"))
        self.client.post(reverse("panel:picture_recheck"))
        self.part.refresh_from_db()
        self.assertEqual(self.part.catalog_picture, "")

    def test_report_needs_staff(self):
        self.client.logout()
        r = self.client.post(reverse("panel:picture_report"), json.dumps({"results": {str(self.part.pk): "none"}}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 302)
        self.part.refresh_from_db()
        self.assertEqual(self.part.catalog_picture, "")
