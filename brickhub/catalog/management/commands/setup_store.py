from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Повне розгортання: міграції, довідковий каталог, структура магазину та демо-товари."

    def add_arguments(self, parser):
        parser.add_argument("--no-demo", action="store_true", help="Без демонстраційних товарів")

    def handle(self, *args, **opts):
        call_command("migrate", interactive=False)
        call_command("import_catalog")
        if not opts["no_demo"]:
            call_command("seed_demo")
        self.stdout.write(self.style.SUCCESS(
            "Готово. Створіть адміністратора: python manage.py createsuperuser"))
