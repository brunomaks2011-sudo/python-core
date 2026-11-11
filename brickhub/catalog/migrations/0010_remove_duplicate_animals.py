"""Removes a second «Тварини» category under «Деталі LEGO» (one added by hand next to the built-in one).

Everything that was in it — shop listings, catalogue parts, subcategories — moves to the built-in «Тварини»
first, so nothing loses its category. Nothing happens when there is no duplicate or no built-in category.
"""
from django.db import migrations


def merge_duplicates(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    Part = apps.get_model("catalog", "Part")
    main = Category.objects.filter(slug="tvaryny").first()
    if main is None:
        return
    for cat in Category.objects.filter(parent__slug="detali").exclude(pk=main.pk):
        if cat.name.strip().lower() != "тварини":
            continue
        Product.objects.filter(category=cat).update(category=main)
        Part.objects.filter(category=cat).update(category=main)
        Category.objects.filter(parent=cat).update(parent=main)
        cat.delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0009_photo_background")]

    operations = [migrations.RunPython(merge_duplicates, migrations.RunPython.noop)]
