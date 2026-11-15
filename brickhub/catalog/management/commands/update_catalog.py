from django.core.management.base import BaseCommand, CommandError

from catalog.importer import UPDATE_DIR, add_missing


class Command(BaseCommand):
    help = ("Додає в довідник нові деталі, мініфігурки та Element ID з файлів Rebrickable (parts, minifigs, "
            "elements .csv або .csv.gz). Наявні записи й товари не змінюються.")

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(UPDATE_DIR), help="Папка з файлами (типово data/rebrickable)")
        parser.add_argument("--dry-run", action="store_true", help="Лише порахувати, нічого не записувати")

    def handle(self, *args, **opts):
        from pathlib import Path

        folder = Path(opts["dir"])
        if not folder.is_dir():
            raise CommandError(f"Папки {folder} немає")
        stats = add_missing(folder, dry_run=opts["dry_run"])
        if not stats:
            raise CommandError(f"У папці {folder} немає parts / minifigs / elements (.csv або .csv.gz)")
        labels = {"parts": "Деталі", "minifigs": "Мініфігурки", "elements": "Element ID"}
        for key, label in labels.items():
            if key in stats:
                added, had = stats[key]
                self.stdout.write(f"  {label}: додано {added}, вже були {had}")
        if stats.get("elements_skipped"):
            self.stdout.write(f"  Element ID пропущено (деталі або кольору немає в довіднику): "
                              f"{stats['elements_skipped']}")
        self.stdout.write(self.style.WARNING("Пробний запуск: нічого не записано.") if opts["dry_run"]
                          else self.style.SUCCESS("Довідник оновлено. Товари не змінювались."))
