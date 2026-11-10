"""Automatic removal of a plain photo background (the photo with the background is always kept)."""
import io
import random
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from accounts.models import User
from catalog.background import remove_background
from catalog.models import ProductImage

from .factories import base_catalog, set_product


def scene(kind="plain", size=(800, 600)):
    """A phone-like photo of a red brick: plain light background with uneven light and a soft shadow."""
    w, h = size
    if kind == "busy":
        rnd = random.Random(3)
        img = Image.new("RGB", size, (90, 120, 160))
        d = ImageDraw.Draw(img)
        for _ in range(250):
            x, y, r = rnd.randrange(w), rnd.randrange(h), rnd.randrange(10, 60)
            d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(rnd.randrange(256) for _ in range(3)))
    else:
        img = Image.composite(Image.new("RGB", size, (204, 203, 200)), Image.new("RGB", size, (245, 244, 241)),
                              Image.linear_gradient("L").resize(size))
    box = (-20, -20, w + 20, int(h * 0.9)) if kind == "fill" else (int(w * 0.3), int(h * 0.32), int(w * 0.7), int(h * 0.66))
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).ellipse((box[0] + 10, box[3] - 30, box[2] + 10, box[3] + 30), fill=90)
    img = Image.composite(Image.new("RGB", size, (40, 40, 45)), img, shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=(201, 26, 9), outline=(110, 12, 4), width=3)
    d.rectangle((box[0], box[1], box[2], box[1] + (box[3] - box[1]) // 3), fill=(226, 60, 40), outline=(110, 12, 4), width=3)
    img = ImageChops.add(img, Image.effect_noise(size, 6).convert("RGB"), 1, -128)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def opened(data):
    return Image.open(io.BytesIO(data))


class BackgroundRemovalTests(TestCase):
    def test_plain_background_becomes_transparent(self):
        result = remove_background(opened(scene()))
        self.assertEqual(result.status, "removed")
        out = result.image
        self.assertEqual(out.mode, "RGBA")
        self.assertLess(out.width, 800)                          # cropped to the object
        alpha = out.getchannel("A")
        self.assertEqual(alpha.getpixel((2, 2)), 0)              # background corner
        self.assertEqual(alpha.getpixel((out.width // 2, out.height // 3)), 255)  # the brick
        r, g, b, _a = out.getpixel((out.width // 2, out.height // 3))
        self.assertGreater(r, 150)
        self.assertLess(g, 90)

    def test_busy_background_or_object_filling_the_photo_is_left_alone(self):
        self.assertEqual(remove_background(opened(scene("busy"))).status, "skipped")
        self.assertEqual(remove_background(opened(scene("fill"))).status, "skipped")

    def test_already_transparent_photo(self):
        img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((80, 50, 220, 150), fill=(200, 30, 10, 255))
        self.assertEqual(remove_background(img).status, "transparent")


class PhotoUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()
        cls.xwing = set_product()
        cls.staff = User.objects.create_user("photo2@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.staff)

    def upload(self, data):
        form = self.client.get(reverse("panel:product_edit", args=[self.xwing.pk])).context["form"]
        post = {k: v for k, v in form.initial.items() if v is not None and not hasattr(v, "pk")}
        post.update({"kind": "set", "condition": "new", "set_number": "75355", "price": "8999", "quantity": 5,
                     "is_active": "on", "images": SimpleUploadedFile("photo.jpg", data, content_type="image/jpeg")})
        self.assertEqual(self.client.post(reverse("panel:product_edit", args=[self.xwing.pk]), post).status_code, 302)
        return self.xwing.images.order_by("-pk").first()

    def test_upload_removes_background_and_keeps_the_original(self):
        photo = self.upload(scene())
        self.assertEqual(photo.background, ProductImage.BG_REMOVED)
        self.assertEqual(Image.open(photo.image.path).mode, "RGBA")
        self.assertEqual(Image.open(photo.original.path).size, (800, 600))
        self.assertTrue(photo.share_url.endswith(".jpg"))
        page = self.client.get(reverse("panel:product_edit", args=[self.xwing.pk])).content.decode()
        self.assertIn("Без фону", page)
        self.assertIn("Повернути фон", page)

        self.client.post(reverse("panel:image_action", args=[photo.pk]), {"action": "restore_bg"})
        photo.refresh_from_db()
        self.assertEqual((photo.background, Image.open(photo.image.path).mode), (ProductImage.BG_KEPT, "RGB"))
        self.client.post(reverse("panel:image_action", args=[photo.pk]), {"action": "remove_bg"})
        photo.refresh_from_db()
        self.assertEqual(photo.background, ProductImage.BG_REMOVED)

        files = [photo.image.path, photo.thumbnail.path, photo.original.path]
        self.client.post(reverse("panel:image_action", args=[photo.pk]), {"action": "delete"})
        self.assertFalse(any(__import__("os").path.exists(f) for f in files))

    def test_busy_photo_stays_as_it_is_with_a_note(self):
        photo = self.upload(scene("busy"))
        self.assertEqual(photo.background, ProductImage.BG_SKIPPED)
        self.assertTrue(photo.background_note)
        self.assertEqual(Image.open(photo.image.path).mode, "RGB")

    @override_settings(SHOP={"REMOVE_PHOTO_BACKGROUND": False, "NAME": "BRICK HUB", "FREE_DELIVERY_FROM": 2500,
                             "ORDER_NOTIFY_EMAILS": [], "LOW_STOCK_THRESHOLD": 3, "SITE_URL": "http://testserver",
                             "TAGLINE": "", "PHONE": "", "EMAIL": "", "ADDRESS": "", "WORK_HOURS": ""})
    def test_switched_off(self):
        photo = self.upload(scene())
        self.assertEqual(photo.background, "")
        self.assertEqual(Image.open(photo.image.path).mode, "RGB")

    def test_photos_added_earlier_are_processed_on_request(self):
        # as photos were stored before this feature: the uploaded JPEG and its thumbnail, nothing else
        name = default_storage.save("products/2026/01/old-photo.jpg", ContentFile(scene()))
        photo = ProductImage.objects.create(product=self.xwing, image=name, thumbnail=name)
        self.assertEqual(photo.background, "")
        page = self.client.get(reverse("panel:products")).content.decode()
        self.assertIn("Прибрати фон зі старих фото (1)", page)
        self.client.post(reverse("panel:photos_remove_backgrounds"))
        photo.refresh_from_db()
        self.assertEqual(photo.background, ProductImage.BG_REMOVED)
        self.assertTrue(photo.original)
        ProductImage.objects.filter(pk=photo.pk).update(background="")
        out = io.StringIO()
        call_command("remove_photo_backgrounds", stdout=out)
        self.assertIn("Оброблено фото: 1", out.getvalue())
