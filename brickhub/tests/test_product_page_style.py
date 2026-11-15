"""Product page in the lego.com style: availability chosen in the panel, no stock numbers, series logo, age, pieces."""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from catalog.models import Inventory, LegoSet, Product, Theme

from .factories import base_catalog, part_product, set_product

MEDIA = tempfile.mkdtemp()


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (255, 200, 0, 255)).save(buf, "PNG")
    return buf.getvalue()


@override_settings(MEDIA_ROOT=MEDIA)
class ProductPageStyleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.staff = User.objects.create_user("style@example.com", "Correct-horse-1", is_staff=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.set = set_product(qty=37, price="2499")
        LegoSet.objects.filter(pk=self.set.lego_set_id).update(age_min=10, pieces=218)
        self.set.refresh_from_db()

    def page(self, product):
        return self.client.get(product.get_absolute_url()).content.decode()

    def test_no_stock_numbers_only_availability(self):
        html = self.page(self.set)
        self.assertIn('class="pdx-avail is-in">Є в наявності', html)
        self.assertNotIn("37 шт", html)
        self.assertNotIn('max="37"', html)
        Product.objects.filter(pk=self.set.pk).update(availability=Product.AVAILABILITY_LOW)
        self.assertIn('class="pdx-avail is-low">Закінчується', self.page(self.set))
        Inventory.objects.filter(product=self.set).update(quantity=0)
        html = self.page(self.set)
        self.assertIn('class="pdx-avail is-out">Немає в наявності', html)
        self.assertIn('id="notify"', html)

    def test_part_cards_do_not_show_counts(self):
        part = part_product(design="3001", color=self.colors["red"], qty=1234)
        html = self.client.get(reverse("catalog:category", args=["detali"])).content.decode()
        self.assertNotIn("1234", html.replace(part.sku, ""))
        self.assertNotIn("1 234", html)
        self.assertNotIn("1234 шт", self.page(part))

    def test_series_name_age_and_pieces_under_the_button(self):
        html = self.page(self.set)
        facts = html.split('class="pdx-facts"', 1)[1].split('class="pdx-extra"', 1)[0]
        self.assertIn("10+", facts)
        self.assertIn("218", facts)
        self.assertIn("Star Wars", facts)  # no logo uploaded yet: the series name
        self.assertIn('class="pdx-number">#75355', html)

    def test_series_logo_uploaded_in_the_panel(self):
        theme = self.set.theme
        root = theme
        while root.parent_id:
            root = root.parent
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:crud_edit", args=["themes", root.pk]), {
            "name": root.name, "title": root.title, "slug": root.slug, "accent": root.accent, "sort_order": 1,
            "is_primary": "on" if root.is_primary else "",
            "logo": SimpleUploadedFile("sw.png", png_bytes(), content_type="image/png")})
        self.assertEqual(r.status_code, 302)
        root.refresh_from_db()
        self.assertTrue(root.logo.name.startswith("themes/"))
        self.assertEqual(Theme.objects.get(pk=theme.pk).brand, root)
        facts = self.page(self.set).split('class="pdx-facts"', 1)[1].split('class="pdx-extra"', 1)[0]
        self.assertIn(root.logo.url, facts)
        self.assertIn("/media/themes/", self.client.get(reverse("panel:crud_list", args=["themes"])).content.decode())

    def test_availability_in_the_panel(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_bulk"), {"ids": [self.set.pk], "action": "running_low"})
        self.assertEqual(r.status_code, 302)
        self.set.refresh_from_db()
        self.assertEqual(self.set.availability, Product.AVAILABILITY_LOW)
        form = self.client.get(reverse("panel:product_edit", args=[self.set.pk])).content.decode()
        self.assertIn('name="availability"', form)

    def test_add_to_cart_button_submits_the_quantity(self):
        html = self.page(self.set)
        self.assertIn('id="buy-form"', html)
        self.assertIn('form="buy-form"', html)
        r = self.client.post(reverse("cart:add"), {"product": self.set.pk, "quantity": 50})
        self.assertEqual(r.status_code, 302)
        cart = self.client.get(reverse("cart:detail")).content.decode()
        self.assertNotIn("лише 37", cart)
