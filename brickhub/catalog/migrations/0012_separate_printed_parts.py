"""«Окремий товар, не варіант кольору»: printed minifigure parts (torsos, heads, legs ...) share one Design ID but
are different items. Listings of parts from «Частини мініфігурок» and «Частини мініляльок» get the flag, so they
stop showing up as colours of each other. Nothing else about the listings changes.
"""

from django.db import migrations, models


def mark_printed_parts(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Product = apps.get_model("catalog", "Product")
    ids, frontier = [], list(Category.objects.filter(slug__in=["chastyny-minifihurok", "chastyny-minilialok"])
                             .values_list("pk", flat=True))
    while frontier:
        ids += frontier
        frontier = list(Category.objects.filter(parent_id__in=frontier).exclude(pk__in=ids).values_list("pk", flat=True))
    if ids:
        Product.objects.filter(kind="part").filter(
            models.Q(category_id__in=ids) | models.Q(part__category_id__in=ids)).update(standalone=True)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0011_product_second_series"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="standalone",
            field=models.BooleanField(
                default=False,
                help_text="Для деталей з принтом (торси, голови, ноги): не показувати разом з іншими кольорами цієї деталі",
                verbose_name="Окремий товар, не варіант кольору",
            ),
        ),
        migrations.RunPython(mark_printed_parts, migrations.RunPython.noop),
    ]
