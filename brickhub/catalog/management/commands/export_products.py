from django.core.management.base import BaseCommand

from panel.excel_export import save_products_workbook


class Command(BaseCommand):
    help = ("Зберігає всі товари в таблицю Excel: назва, номери LEGO і BrickLink, Element ID, колір, стан, "
            "кількість, ціна, місце на складі. Типово — у папку exports/.")

    def add_arguments(self, parser):
        parser.add_argument("--out", help="Куди зберегти, напр. tovary.xlsx")

    def handle(self, *args, **opts):
        path, count = save_products_workbook(opts.get("out"))
        self.stdout.write(self.style.SUCCESS(f"Збережено товарів: {count}"))
        self.stdout.write(f"Файл: {path}")
