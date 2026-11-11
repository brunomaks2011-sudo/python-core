"""Console commands that ask for the e-mail and password, and removing a hand-made second «Тварини»."""
import importlib
import io
from unittest import mock

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import User
from catalog.models import Category, Part, Product

from .factories import base_catalog, part_product


def run(command, answers, passwords):
    out = io.StringIO()
    with mock.patch("builtins.input", side_effect=answers), \
            mock.patch("getpass.getpass", side_effect=passwords):
        call_command(command, stdout=out)
    return out.getvalue()


class AccountCommandTests(TestCase):
    def test_change_login_asks_for_new_email_name_and_password(self):
        User.objects.create_superuser("old@example.com", "Old-password-1")
        out = run("change_login", ["new@example.com", "Максим"], ["short", "short", "Brick-hub-2026", "Brick-hub-2026"])
        self.assertIn("Готово. Вхід: new@example.com з новим паролем", out)
        user = User.objects.get()
        self.assertEqual((user.email, user.first_name), ("new@example.com", "Максим"))
        self.assertTrue(user.check_password("Brick-hub-2026"))

    def test_change_login_can_keep_the_password(self):
        User.objects.create_superuser("boss@example.com", "Old-password-1")
        run("change_login", ["", ""], [""])  # Enter everywhere: nothing changes
        user = User.objects.get()
        self.assertEqual(user.email, "boss@example.com")
        self.assertTrue(user.check_password("Old-password-1"))

    def test_add_admin_creates_a_staff_account(self):
        out = run("add_admin", ["partner@example.com", "Олег"], ["Lego-partner-7", "Lego-other-7", "Lego-partner-7",
                                                                 "Lego-partner-7"])
        self.assertIn("Олег входить у панель", out)
        user = User.objects.get(email="partner@example.com")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("Lego-partner-7"))

    def test_add_admin_gives_access_to_an_existing_buyer(self):
        User.objects.create_user("buyer@example.com", "Buyer-pass-1")
        run("add_admin", ["buyer@example.com", "так", "Олег"], ["Lego-partner-7", "Lego-partner-7"])
        user = User.objects.get(email="buyer@example.com")
        self.assertTrue(user.is_staff)
        with self.assertRaises(CommandError):
            run("add_admin", ["buyer@example.com", "ні"], [])


class DuplicateAnimalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.colors = base_catalog()

    def test_second_animals_category_is_merged_into_the_built_in_one(self):
        main = Category.objects.get(slug="tvaryny")
        detali = Category.objects.get(slug="detali")
        dup = Category.objects.create(name="Тварини", slug="tvaryny-moi", kind="part", parent=detali)
        listing = part_product(design="horse-d", name="Horse", name_uk="Кінь", color=self.colors["red"])
        Product.objects.filter(pk=listing.pk).update(category=dup)
        Part.objects.filter(pk=listing.part_id).update(category=dup)
        importlib.import_module("catalog.migrations.0010_remove_duplicate_animals").merge_duplicates(apps, None)
        self.assertFalse(Category.objects.filter(pk=dup.pk).exists())
        self.assertTrue(Category.objects.filter(pk=main.pk).exists())
        listing.refresh_from_db()
        self.assertEqual(listing.category, main)
        self.assertEqual(Part.objects.get(pk=listing.part_id).category, main)
