"""Finds the BrickLink number and the LEGO Element IDs of every part on sale, via the Rebrickable API.

Only numbers are taken (no pictures). For each part listed in the shop it asks Rebrickable:
* the part's numbers in other catalogues — when its BrickLink number differs from the Design ID, it is saved;
* the Element IDs of the part in each colour on sale — they are saved for that part and colour.
Pictures then come from BrickLink (by the right number) or, failing that, from LEGO (by the Element ID).

A free API key: rebrickable.com → sign up → Settings → API → Generate new key.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Element, Part, Product

API = "https://rebrickable.com/api/v3/lego"
PAUSE = 1.05  # Rebrickable allows about one request per second


class NotFound(Exception):
    pass


def get_json(url: str, key: str) -> dict:
    """GET a Rebrickable API URL; retries when throttled. Raises NotFound for 404."""
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"Authorization": f"key {key}", "Accept": "application/json",
                                                       "User-Agent": "BrickHub-shop/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url) from None
            if e.code == 429 and attempt < 3:
                wait = e.headers.get("Retry-After") if e.headers else None
                time.sleep(min(60, int(wait)) if wait and wait.isdigit() else 5 * (attempt + 1))
                continue
            if e.code in (401, 403):
                raise CommandError("Rebrickable не прийняв ключ API. Перевірте ключ (Settings → API на rebrickable.com).")
            raise CommandError(f"Rebrickable відповів помилкою {e.code} на {url}")
        except urllib.error.URLError as e:
            raise CommandError(
                f"Немає з'єднання з rebrickable.com ({e.reason}). Якщо сайт на безкоштовному PythonAnywhere, "
                "перевірте, що rebrickable.com є в списку дозволених сайтів (Help → «whitelist»).")
    raise CommandError("Rebrickable довго не відповідає, спробуйте пізніше")


class Command(BaseCommand):
    help = ("Знаходить номер BrickLink і Element ID для кожної деталі в продажу через Rebrickable API "
            "(лише номери, без картинок). Ключ: --key або змінна REBRICKABLE_API_KEY.")

    def add_arguments(self, parser):
        parser.add_argument("--key", help="ключ Rebrickable API (rebrickable.com → Settings → API)")
        parser.add_argument("--dry-run", action="store_true", help="лише показати, що буде змінено")
        parser.add_argument("--refresh", action="store_true",
                            help="перевірити й деталі, у яких уже є номер BrickLink / Element ID")

    def handle(self, *args, **opts):
        key = (opts.get("key") or os.environ.get("REBRICKABLE_API_KEY") or "").strip()
        if not key:
            raise CommandError("Потрібен ключ Rebrickable API: --key ВАШ_КЛЮЧ "
                               "(безкоштовно: rebrickable.com → Settings → API → Generate new key)")
        dry, refresh = opts["dry_run"], opts["refresh"]
        pairs = (Product.objects.filter(kind="part", part__isnull=False, color__isnull=False)
                 .values_list("part_id", "color_id", "color__rebrickable_id").distinct())
        colours_by_part: dict[int, set] = {}
        for part_id, color_id, rb_color in pairs:
            colours_by_part.setdefault(part_id, set()).add((color_id, rb_color))
        have_element = set(Element.objects.values_list("part_id", "color_id"))
        parts = Part.objects.filter(pk__in=colours_by_part).order_by("design_id")
        self.stdout.write(f"Деталей у продажу: {parts.count()}. Rebrickable відповідає ~1 раз на секунду, "
                          "тож це займе кілька хвилин.")
        stats = {"bricklink": 0, "elements": 0, "missing": 0, "requests": 0}
        changed_parts = set()
        for part in parts.iterator():
            number = urllib.parse.quote(part.design_id, safe="")
            if refresh or not part.bricklink_no:
                try:
                    info = get_json(f"{API}/parts/{number}/", key)
                except NotFound:
                    stats["missing"] += 1
                    self.stdout.write(f"  {part.design_id}: немає в Rebrickable — перевірте Design ID")
                    continue
                finally:
                    stats["requests"] += 1
                    time.sleep(PAUSE)
                bl_numbers = (info.get("external_ids") or {}).get("BrickLink") or []
                if bl_numbers and part.design_id not in bl_numbers and part.bricklink_no != bl_numbers[0]:
                    self.stdout.write(f"  {part.design_id}: на BrickLink це {bl_numbers[0]}")
                    stats["bricklink"] += 1
                    if not dry:
                        part.bricklink_no = bl_numbers[0][:60]
                        part.save(update_fields=["bricklink_no"])
                        changed_parts.add(part.pk)
            for color_id, rb_color in sorted(colours_by_part[part.pk], key=lambda c: c[0]):
                if rb_color is None or (not refresh and (part.pk, color_id) in have_element):
                    continue
                try:
                    data = get_json(f"{API}/parts/{number}/colors/{rb_color}/", key)
                except NotFound:
                    continue
                finally:
                    stats["requests"] += 1
                    time.sleep(PAUSE)
                for element in data.get("elements") or []:
                    element = str(element)[:20]
                    owner = Element.objects.filter(element_id=element).first()
                    if owner is not None:
                        continue  # already known (for this or another part — never moved)
                    stats["elements"] += 1
                    if not dry:
                        Element.objects.create(element_id=element, part=part, color_id=color_id)
                        changed_parts.add(part.pk)
        if not dry:
            for listing in Product.objects.filter(part_id__in=changed_parts):
                listing.save(update_fields=["search_text"])  # numbers are part of the search index
        verb = "Буде додано" if dry else "Додано"
        self.stdout.write(self.style.SUCCESS(
            f"{verb}: номерів BrickLink {stats['bricklink']}, Element ID {stats['elements']}. "
            f"Не знайдено в Rebrickable: {stats['missing']}. Запитів: {stats['requests']}."))
