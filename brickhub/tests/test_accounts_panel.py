import io

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import User
from catalog.models import Inventory, Product
from orders.models import Order

from .factories import base_catalog, part_product, set_product


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        base_catalog()
        cls.xwing = set_product(qty=3)

    def setUp(self):
        cache.clear()

    def test_register_login_logout(self):
        r = self.client.post(reverse("accounts:register"), {
            "first_name": "Олена", "last_name": "Коваль", "email": "Olena@Example.com", "phone": "0501112233",
            "password1": "LegoFan-2026!", "password2": "LegoFan-2026!", "agree": "on"})
        self.assertRedirects(r, reverse("accounts:dashboard"))
        user = User.objects.get()
        self.assertEqual(user.email, "olena@example.com")
        self.assertEqual(user.phone, "+380501112233")
        self.assertNotEqual(user.password, "LegoFan-2026!")  # hashed
        self.client.post(reverse("accounts:logout"))
        r = self.client.post(reverse("accounts:login"), {"email": "OLENA@example.com", "password": "LegoFan-2026!"})
        self.assertRedirects(r, reverse("accounts:dashboard"))

    def test_login_lockout(self):
        User.objects.create_user("a@example.com", "Correct-horse-1")
        for _ in range(8):
            self.client.post(reverse("accounts:login"), {"email": "a@example.com", "password": "wrong"})
        r = self.client.post(reverse("accounts:login"), {"email": "a@example.com", "password": "Correct-horse-1"})
        self.assertContains(r, "Забагато невдалих спроб")

    def test_guest_cart_merges_on_login(self):
        User.objects.create_user("b@example.com", "Correct-horse-1")
        self.client.post(reverse("cart:add"), {"product": self.xwing.pk, "quantity": 2})
        self.client.post(reverse("accounts:login"), {"email": "b@example.com", "password": "Correct-horse-1"})
        r = self.client.get(reverse("cart:detail"))
        self.assertContains(r, "X-Wing Starfighter")

    def test_orders_are_private(self):
        owner = User.objects.create_user("c@example.com", "Correct-horse-1")
        other = User.objects.create_user("d@example.com", "Correct-horse-1")
        order = Order.objects.create(user=owner, first_name="C", last_name="C", phone="+380671234567",
                                     email="c@example.com", delivery_method="np_warehouse", city="Київ",
                                     np_warehouse="1", payment_method="cod", total=100)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("accounts:order_detail", args=[order.number])).status_code, 404)
        self.client.force_login(owner)
        self.assertEqual(self.client.get(reverse("accounts:order_detail", args=[order.number])).status_code, 200)


class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        cls.part = part_product(color=cls.colors["red"], qty=10, price="6.00")
        set_product()
        cls.staff = User.objects.create_user("staff@example.com", "Correct-horse-1", is_staff=True)
        cls.customer = User.objects.create_user("cust@example.com", "Correct-horse-1")

    def test_access_control(self):
        url = reverse("panel:dashboard")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_csv_import_dry_run_then_apply(self):
        self.client.force_login(self.staff)
        csv_text = ("design_id;color_id;condition;quantity;price;location\n"
                    "3001;5;new;40;6,50;A-1\n"      # update existing lot
                    "3001;11;used;7;4;B-2\n"        # new lot (black, used)
                    "NOPE-123;5;new;1;1;\n")        # unknown part -> error
        f = io.BytesIO(csv_text.encode("cp1251"))
        f.name = "parts.csv"
        r = self.client.post(reverse("panel:import"), {"kind": "auto", "mode": "check", "file": f})
        self.assertContains(r, "немає в каталозі")
        self.assertEqual(Inventory.objects.get(product=self.part).quantity, 10)  # dry run changed nothing
        f = io.BytesIO(csv_text.encode("cp1251"))
        f.name = "parts.csv"
        self.client.post(reverse("panel:import"), {"kind": "auto", "mode": "apply", "file": f})
        self.part.refresh_from_db()
        self.assertEqual(str(self.part.price), "6.50")
        self.assertEqual(Inventory.objects.get(product=self.part).quantity, 40)
        used = Product.objects.get(part__design_id="3001", color__bricklink_id=11, condition="used")
        self.assertEqual(used.inventory.quantity, 7)
        self.assertEqual(used.inventory.location, "B-2")

    def test_xlsx_stock_update(self):
        self.client.force_login(self.staff)
        wb = Workbook()
        ws = wb.active
        ws.append(["sku", "quantity", "price"])
        ws.append([self.part.sku, 99, 7.25])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "stock.xlsx"
        self.client.post(reverse("panel:import"), {"kind": "auto", "mode": "apply", "file": buf})
        self.part.refresh_from_db()
        self.assertEqual(str(self.part.price), "7.25")
        self.assertEqual(self.part.inventory.quantity, 99)

    def test_product_form_validates_numbers(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_new"), {"kind": "set", "condition": "new", "set_number": "123456789",
                                                           "price": "100", "quantity": 1})
        self.assertContains(r, "немає в каталозі")
        r = self.client.post(reverse("panel:product_new"), {"kind": "set", "condition": "used", "set_number": "75355",
                                                           "price": "5000", "quantity": 1, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Product.objects.filter(lego_set__number="75355-1", condition="used").exists())

    def test_quick_update_and_export(self):
        self.client.force_login(self.staff)
        r = self.client.post(reverse("panel:product_quick_update", args=[self.part.pk]), {"price": "5,50", "quantity": "3"},
                             HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(r.json()["quantity"], 3)
        r = self.client.get(reverse("panel:export_products"))
        body = b"".join(r.streaming_content).decode("utf-8")
        self.assertIn(self.part.sku, body)


class KeychainBookAndSearchablePickerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()
        from catalog.models import Minifigure

        cls.fig = Minifigure.objects.create(fig_number="fig-000001", name="Toy Store Employee")
        cls.staff = User.objects.create_user("staff2@example.com", "Correct-horse-1", is_staff=True)

    def setUp(self):
        self.client.force_login(self.staff)

    def test_new_kinds_and_sections_exist(self):
        from catalog.models import Category

        self.assertTrue(Category.objects.filter(slug="breloky", kind="keychain", parent=None).exists())
        self.assertTrue(Category.objects.filter(slug="knyhy-z-fihurkamy", kind="book", parent=None).exists())
        r = self.client.get(reverse("panel:product_new"))
        self.assertContains(r, '<option value="keychain">Брелок</option>', html=True)
        self.assertContains(r, '<option value="book">Книга з фігуркою</option>', html=True)

    def test_keychain_without_number_goes_to_its_section(self):
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "keychain", "condition": "new", "title": "Брелок Дарт Вейдер", "price": "349", "quantity": 4,
            "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        p = Product.objects.get(kind="keychain")
        self.assertEqual(p.category.slug, "breloky")
        self.assertTrue(p.sku.startswith("BH-K-"))
        self.assertContains(self.client.get(reverse("catalog:category", args=["breloky"])), "Брелок Дарт Вейдер")

    def test_book_with_included_minifigure(self):
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "book", "condition": "new", "title": "Книга LEGO з фігуркою", "fig_number": "fig-000001",
            "price": "599", "quantity": 2, "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        book = Product.objects.get(kind="book")
        self.assertEqual(book.minifigure, self.fig)
        self.assertEqual(book.category.slug, "knyhy-z-fihurkamy")
        page = self.client.get(book.get_absolute_url())
        self.assertContains(page, "Мініфігурка в комплекті")
        self.assertContains(page, "Toy Store Employee")
        # an unknown figure number is refused, a missing one is fine
        r = self.client.post(reverse("panel:product_new"), {
            "kind": "book", "condition": "new", "title": "Інша книга", "fig_number": "nope-404", "price": "1",
            "quantity": 1})
        self.assertContains(r, "Такої мініфігурки немає в каталозі")

    def test_colour_picker_is_searchable(self):
        r = self.client.get(reverse("panel:product_new") + "?kind=part")
        html = r.content.decode()
        self.assertIn('data-searchable="1"', html)
        self.assertIn('data-hex="#C91A09"', html)
        self.assertIn("Червоний (Red) · 5", html)
