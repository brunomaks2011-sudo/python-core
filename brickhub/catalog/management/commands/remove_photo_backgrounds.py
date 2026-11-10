from django.core.management.base import BaseCommand

from catalog.images import photos_to_process, remove_photo_background
from catalog.models import ProductImage


class Command(BaseCommand):
    help = ("Прибирає однотонний фон з фото товарів, доданих раніше (оригінали з фоном зберігаються, "
            "фон можна повернути в панелі). --all — обробити наново всі завантажені фото.")

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="обробити всі завантажені фото, а не лише нові")

    def handle(self, *args, **opts):
        qs = (ProductImage.objects.exclude(image="").exclude(background=ProductImage.BG_KEPT)
              if opts["all"] else photos_to_process())
        total = removed = 0
        for photo in qs.order_by("pk").iterator():
            note = remove_photo_background(photo)
            total += 1
            removed += photo.background == ProductImage.BG_REMOVED
            self.stdout.write(f"{photo.product.sku}: {note}")
        self.stdout.write(self.style.SUCCESS(f"Оброблено фото: {total}, фон прибрано на {removed}"))
