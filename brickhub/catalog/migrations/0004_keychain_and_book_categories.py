"""Adds the "Брелоки" and "Книги з фігурками" shop sections.

Only creates the two categories when they are missing; existing products and
categories are not touched.
"""
from django.db import migrations

NEW_ROOTS = [
    ("breloky", "Брелоки", "keychain", "key", "Брелоки LEGO: мініфігурки, цеглинки та герої улюблених серій.", 24),
    ("knyhy-z-fihurkamy", "Книги з фігурками", "book", "book",
     "Книги LEGO з ексклюзивною мініфігуркою в комплекті.", 26),
]


def add_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for slug, name, kind, icon, description, order in NEW_ROOTS:
        if not Category.objects.filter(slug=slug).exists():
            Category.objects.create(slug=slug, name=name, kind=kind, icon=icon, description=description,
                                    sort_order=order, parent=None, is_active=True)


def remove_categories(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Category.objects.filter(slug__in=[r[0] for r in NEW_ROOTS], products__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_keychain_and_book_kinds")]

    operations = [migrations.RunPython(add_categories, remove_categories)]
