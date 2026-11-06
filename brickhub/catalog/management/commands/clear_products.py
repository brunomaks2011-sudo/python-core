from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cart.models import PromoCode
from catalog.models import Product, ProductImage


class Command(BaseCommand):
    help = (
        "Видаляє всі товари магазину (разом із фото, залишками, відгуками, обраним і позиціями кошиків). "
        "Довідковий каталог LEGO (номери наборів, деталей, кольори) залишається. Замовлення зберігаються."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Не питати підтвердження")
        parser.add_argument("--promo", action="store_true", help="Також видалити всі промокоди")

    def handle(self, *args, **opts):
        total = Product.objects.count()
        promos = PromoCode.objects.count() if opts["promo"] else 0
        if not total and not promos:
            self.stdout.write("Товарів немає — нічого видаляти.")
            return
        if not opts["yes"]:
            answer = input(f"Видалити {total} товарів{f' і {promos} промокодів' if promos else ''}? Введіть yes: ")
            if answer.strip().lower() != "yes":
                raise CommandError("Скасовано.")
        files = 0
        for photo in ProductImage.objects.exclude(image="").iterator():
            for field in (photo.image, photo.thumbnail):
                if field:
                    field.delete(save=False)
                    files += 1
        with transaction.atomic():
            Product.objects.all().delete()
            if opts["promo"]:
                PromoCode.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(
            f"Видалено товарів: {total}, файлів фото: {files}" + (f", промокодів: {promos}" if promos else "")))
