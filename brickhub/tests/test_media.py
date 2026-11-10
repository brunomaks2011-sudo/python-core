"""Uploaded product photos must be reachable on a production server (DEBUG off) without web-server config."""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from catalog.models import Product

from .factories import base_catalog, set_product


def png_upload(name="photo.png", size=(900, 700)):
    buf = io.BytesIO()
    Image.new("RGB", size, (201, 26, 9)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class ProductPhotoServingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()
        cls.xwing = set_product()
        cls.staff = User.objects.create_user("photos@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def test_photo_added_in_panel_is_served_and_shown(self):
        self.client.force_login(self.staff)
        form = self.client.get(reverse("panel:product_edit", args=[self.xwing.pk])).context["form"]
        data = {k: v for k, v in form.initial.items() if v is not None and not hasattr(v, "pk")}
        data.update({"kind": "set", "condition": "new", "set_number": "75355", "price": "8999", "quantity": 5,
                     "is_active": "on", "images": png_upload()})
        r = self.client.post(reverse("panel:product_edit", args=[self.xwing.pk]), data)
        self.assertEqual(r.status_code, 302)
        photo = Product.objects.get(pk=self.xwing.pk).images.get()
        self.assertTrue(photo.image and photo.thumbnail)
        self.client.logout()

        page = self.client.get(self.xwing.get_absolute_url()).content.decode()
        self.assertIn(photo.url, page)
        for url, ctype in ((photo.url, "image/png"), (photo.thumb_url, "image/webp")):
            r = self.client.get(url)  # tests run with DEBUG off, like the live site
            self.assertEqual(r.status_code, 200, url)
            self.assertEqual(r["Content-Type"], ctype)
            self.assertIn("max-age", r["Cache-Control"])
            r.close()

    def test_only_product_photos_are_reachable(self):
        with open(f"{self.media}/notes.txt", "w") as fh:
            fh.write("private")
        self.assertEqual(self.client.get("/media/notes.txt").status_code, 404)
        self.assertEqual(self.client.get("/media/products/missing.jpg").status_code, 404)
        self.assertIn(self.client.get("/media/products/../notes.txt").status_code, (400, 404))
