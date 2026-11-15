from django.core.management.base import BaseCommand

from catalog.models import ProductImage


class Command(BaseCommand):
    help = ("Видаляє всі фото, додані в панелі (файли та посилання). Після цього товари показують картинки з "
            "каталогу BrickLink. Без --yes лише показує, скільки фото буде видалено.")

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="справді видалити (інакше лише перевірка)")

    def handle(self, *args, **opts):
        photos = ProductImage.objects.all()
        total = photos.count()
        products = photos.values("product_id").distinct().count()
        if not opts["yes"]:
            self.stdout.write(f"Буде видалено фото: {total} (у {products} товарах). Нічого не змінено.\n"
                              "Щоб видалити, запустіть ще раз з --yes")
            return
        for photo in photos.iterator():
            photo.delete_files()
        photos.delete()
        self.stdout.write(self.style.SUCCESS(f"Видалено фото: {total} (у {products} товарах). "
                                             "Тепер товари показують картинки з BrickLink."))
