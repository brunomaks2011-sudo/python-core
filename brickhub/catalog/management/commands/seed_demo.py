from django.core.management.base import BaseCommand

from catalog.demo import seed_demo


class Command(BaseCommand):
    help = "Створює демонстраційні товари магазину з реальних даних каталогу (ціни та залишки — демо)."

    def add_arguments(self, parser):
        parser.add_argument("--with-catalog-images", action="store_true",
                            help="Додати до демо-товарів посилання на фото з каталогу Rebrickable")

    def handle(self, *args, **opts):
        stats = seed_demo(with_images=opts["with_catalog_images"])
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Демо-товари створено."))
