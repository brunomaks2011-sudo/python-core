"""Adds the "Тварини" part category (animals, creatures, their body parts and accessories).

Only reference catalogue parts are moved into it (and only those that were in
"Інші елементи" or had no category); shop products keep the category they have.
"""
from django.db import migrations

ANIMAL_PART_CATEGORIES = [28, 74, 75]  # Rebrickable: Animals / Creatures, Animal Accessories, Animal Body Parts


def add_animals(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    animals = Category.objects.filter(slug="tvaryny").first()
    if animals is None:
        animals = Category.objects.create(
            slug="tvaryny", name="Тварини", kind="part", icon="animal", sort_order=95, is_active=True,
            parent=Category.objects.filter(slug="detali").first(),
            description="Тварини, птахи, риби та фантастичні істоти, їхні частини тіла й аксесуари.",
            rebrickable_part_categories=",".join(map(str, ANIMAL_PART_CATEGORIES)))
    parts = Part.objects.filter(part_category_id__in=ANIMAL_PART_CATEGORIES)
    parts.filter(category__isnull=True).update(category=animals)
    other = Category.objects.filter(slug="inshi-elementy").first()
    if other is not None:
        parts.filter(category=other).update(category=animals)


def remove_animals(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Part = apps.get_model("catalog", "Part")
    animals = Category.objects.filter(slug="tvaryny").first()
    if animals is None:
        return
    other = Category.objects.filter(slug="inshi-elementy").first()
    Part.objects.filter(category=animals).update(category=other)
    if not animals.products.exists():
        animals.delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_keychain_and_book_categories")]

    operations = [migrations.RunPython(add_animals, remove_animals)]
