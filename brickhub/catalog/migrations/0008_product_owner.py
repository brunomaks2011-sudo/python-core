"""«Чий товар»: the owner of a listing (the shop owner or a partner who sells his goods through the shop).

Existing listings get the staff member who first put them in stock (the first manual change or import in the
stock log). Listings without such a record stay "не вказано" — they can be assigned in the panel.
Nothing else about the listings changes.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_owners(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Movement = apps.get_model("catalog", "InventoryMovement")
    first = {}
    rows = (Movement.objects.filter(user__is_staff=True, reason__in=["manual", "import", "restock"])
            .order_by("created_at", "id").values_list("inventory__product_id", "user_id"))
    for product_id, user_id in rows.iterator():
        first.setdefault(product_id, user_id)
    by_user = {}
    for product_id, user_id in first.items():
        by_user.setdefault(user_id, []).append(product_id)
    for user_id, ids in by_user.items():
        for i in range(0, len(ids), 500):
            Product.objects.filter(pk__in=ids[i:i + 500], owner__isnull=True).update(owner_id=user_id)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_part_subcategories"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"is_staff": True},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_products",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Чий товар",
            ),
        ),
        migrations.RunPython(fill_owners, migrations.RunPython.noop),
    ]
