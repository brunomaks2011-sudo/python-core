from django.core.management.base import BaseCommand

from catalog.importer import DEFAULT_FILE, import_bundle, import_rebrickable_csv


class Command(BaseCommand):
    help = "Імпорт довідкового каталогу LEGO (кольори, серії, деталі, набори, мініфігурки)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="Файл catalog_full.json.gz")
        parser.add_argument("--csv-dir", help="Папка з CSV-файлами Rebrickable (colors.csv, parts.csv, elements.csv ...)")

    def handle(self, *args, **opts):
        if opts.get("csv_dir"):
            stats = import_rebrickable_csv(opts["csv_dir"])
        else:
            stats = import_bundle(opts["file"])
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Каталог імпортовано."))
