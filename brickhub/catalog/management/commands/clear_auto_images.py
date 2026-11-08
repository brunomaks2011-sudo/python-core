from django.core.management.base import BaseCommand
from django.db.models import Q

from catalog.models import ProductImage

CATALOGUE_HOSTS = ("https://cdn.rebrickable.com/", "http://cdn.rebrickable.com/")


class Command(BaseCommand):
    help = ("Прибирає фото, які були підставлені автоматично з каталогу Rebrickable (посилання без завантаженого "
            "файлу). Фото, які ви завантажили самі, не змінюються.")

    def add_arguments(self, parser):
        parser.add_argument("--all-links", action="store_true",
                            help="Прибрати всі фото-посилання без файлу, а не лише з Rebrickable")

    def handle(self, *args, **opts):
        qs = ProductImage.objects.filter(image="").exclude(external_url="")
        if not opts["all_links"]:
            cond = Q()
            for host in CATALOGUE_HOSTS:
                cond |= Q(external_url__startswith=host)
            qs = qs.filter(cond)
        n = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Прибрано автоматичних фото: {n}"))
