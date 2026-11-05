from django.core.management.base import BaseCommand

from catalog.models import Product


class Command(BaseCommand):
    help = "Перебудовує пошуковий індекс товарів (після імпорту Element ID тощо)."

    def handle(self, *args, **opts):
        n = 0
        qs = Product.objects.select_related("lego_set", "part", "color", "minifigure", "theme", "category")
        for product in qs.iterator(chunk_size=500):
            text = product.build_search_text()
            if text != product.search_text:
                Product.objects.filter(pk=product.pk).update(search_text=text)
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Оновлено: {n}"))
