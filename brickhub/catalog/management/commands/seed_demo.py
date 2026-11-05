from django.core.management.base import BaseCommand

from catalog.demo import seed_demo


class Command(BaseCommand):
    help = "Створює демонстраційні товари магазину з реальних даних каталогу (ціни та залишки — демо)."

    def add_arguments(self, parser):
        parser.add_argument("--no-images", action="store_true", help="Не додавати посилання на фото з каталогу")

    def handle(self, *args, **opts):
        stats = seed_demo(with_images=not opts["no_images"])
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Демо-товари створено."))
