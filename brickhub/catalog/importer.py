"""Import of the official reference catalogue.

Sources:
* the bundled ``data/catalog_full.json.gz`` (built by tools/build_catalog_data.py);
* a folder with Rebrickable CSV downloads (colors.csv, themes.csv, parts.csv,
  sets.csv, minifigs.csv, elements.csv ... – plain or .gz) from
  https://rebrickable.com/downloads/ – use it to refresh the catalogue or to
  load LEGO Element IDs (elements.csv).
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.db import transaction

from core.utils import make_slug

from .models import Category, Color, Element, LegoSet, Minifigure, Part, PartCategory, Theme

logger = logging.getLogger("brickhub")
BATCH = 2000
DEFAULT_FILE = Path(settings.BASE_DIR) / "data" / "catalog_full.json.gz"
IMAGE_BASE = "https://cdn.rebrickable.com/media/sets/"


def _upsert(model, objs, unique, update):
    for i in range(0, len(objs), BATCH):
        model.objects.bulk_create(objs[i:i + BATCH], update_conflicts=True, unique_fields=unique,
                                  update_fields=update)


def import_colors(rows) -> int:
    """rows: (rb_id, name, rgb, is_trans, bricklink_id)"""
    existing = {c.rebrickable_id: c for c in Color.objects.filter(rebrickable_id__isnull=False)}
    by_name = {c.name.lower(): c for c in Color.objects.all()}
    taken_bl = set(Color.objects.exclude(bricklink_id__isnull=True).values_list("bricklink_id", flat=True))
    n = 0
    for rb_id, name, rgb, is_trans, bl_id in rows:
        color = existing.get(rb_id) or by_name.get(name.lower())
        if color is None:
            color = Color(name=name, rebrickable_id=rb_id)
        color.rebrickable_id = rb_id
        color.rgb = (rgb or "CCCCCC").upper()
        color.is_transparent = bool(is_trans)
        if bl_id and color.bricklink_id is None and bl_id not in taken_bl:
            color.bricklink_id = bl_id
            taken_bl.add(bl_id)
        if rb_id in (-1, 9999):
            color.is_active = False
        if not color.slug:
            base = make_slug(name)
            slug, k = base, 2
            while Color.objects.filter(slug=slug).exclude(pk=color.pk).exists():
                slug, k = f"{base}-{k}", k + 1
            color.slug = slug
        if color.sort_order == 1000 and color.bricklink_id:
            color.sort_order = color.bricklink_id
        color.save()
        n += 1
    return n


def import_themes(rows) -> int:
    """rows: (rb_id, name, parent_rb_id)"""
    names = {r[0]: r[1] for r in rows}
    parents = {r[0]: r[2] for r in rows}
    existing = {t.rebrickable_id: t for t in Theme.objects.filter(rebrickable_id__isnull=False)}
    slugs = set(Theme.objects.values_list("slug", flat=True))
    for rb_id, name, parent in rows:
        theme = existing.get(rb_id)
        if theme is None:
            label = f"{names.get(parent, '')} {name}" if parent else name
            base = make_slug(label)
            slug, k = base, 2
            while slug in slugs:
                slug, k = f"{base}-{k}", k + 1
            slugs.add(slug)
            theme = Theme(rebrickable_id=rb_id, name=name, slug=slug)
            theme.save()
            existing[rb_id] = theme
        elif theme.name != name:
            theme.name = name
            theme.save(update_fields=["name"])
    for rb_id, parent in parents.items():
        theme = existing[rb_id]
        want = existing[parent].pk if parent in existing else None
        # keep shop overrides (series are re-parented by apply_structure)
        if theme.parent_id is None and want and not theme.is_primary:
            Theme.objects.filter(pk=theme.pk).update(parent_id=want)
    return len(rows)


def import_part_categories(rows) -> int:
    objs = [PartCategory(id=rid, name=name) for rid, name in rows]
    _upsert(PartCategory, objs, ["id"], ["name"])
    return len(objs)


def _rb_to_shop_category() -> dict[int, int]:
    mapping = {}
    for cat in Category.objects.filter(kind="part").exclude(rebrickable_part_categories=""):
        for rid in cat.rb_category_ids():
            mapping.setdefault(rid, cat.pk)
    return mapping


def import_parts(rows) -> int:
    """rows: (part_num, name, part_cat_id)"""
    shop_cat = _rb_to_shop_category()
    valid_cats = set(PartCategory.objects.values_list("id", flat=True))
    objs = [
        Part(design_id=num[:40], name=name[:255], part_category_id=cat if cat in valid_cats else None,
             category_id=shop_cat.get(cat))
        for num, name, cat in rows
    ]
    _upsert(Part, objs, ["design_id"], ["name", "part_category"])
    # assign shop categories only where none was chosen manually
    by_cat = defaultdict(list)
    for num, _name, cat in rows:
        if cat in shop_cat:
            by_cat[shop_cat[cat]].append(num)
    for cat_id, nums in by_cat.items():
        for i in range(0, len(nums), 900):
            Part.objects.filter(design_id__in=nums[i:i + 900], category__isnull=True).update(category_id=cat_id)
    return len(objs)


def import_sets(rows) -> int:
    """rows: (set_num, name, year, theme_rb_id, num_parts, minifigs, has_img|img_url)"""
    themes = dict(Theme.objects.filter(rebrickable_id__isnull=False).values_list("rebrickable_id", "pk"))
    objs = []
    for num, name, year, theme_id, parts, figs, img in rows:
        if isinstance(img, str):
            url = img
        else:
            url = f"{IMAGE_BASE}{num.lower()}.jpg" if img else ""
        objs.append(LegoSet(number=num[:40], name=name[:255], year=year or None, theme_id=themes.get(theme_id),
                            pieces=parts or None, minifigs_count=figs if figs is not None else None, image_url=url))
    _upsert(LegoSet, objs, ["number"], ["name", "year", "theme", "pieces", "minifigs_count", "image_url"])
    return len(objs)


def import_minifigs(rows) -> int:
    """rows: (fig_num, name, num_parts)"""
    objs = [Minifigure(fig_number=num[:40], name=name[:255], num_parts=parts or None,
                       image_url=f"{IMAGE_BASE}{num.lower()}.jpg")
            for num, name, parts in rows]
    _upsert(Minifigure, objs, ["fig_number"], ["name", "num_parts", "image_url"])
    return len(objs)


def import_elements(rows) -> int:
    """rows: (element_id, part_num, color_rb_id)"""
    parts = dict(Part.objects.values_list("design_id", "pk"))
    colors = dict(Color.objects.filter(rebrickable_id__isnull=False).values_list("rebrickable_id", "pk"))
    objs = [Element(element_id=str(e)[:20], part_id=parts[p], color_id=colors[c])
            for e, p, c in rows if p in parts and c in colors]
    _upsert(Element, objs, ["element_id"], ["part", "color"])
    return len(objs)


@transaction.atomic
def import_bundle(path: Path | str = DEFAULT_FILE, stdout=None) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    stats = {
        "colors": import_colors(data["colors"]),
        "themes": import_themes(data["themes"]),
        "part_categories": import_part_categories(data["part_categories"]),
    }
    from .structure import apply_structure

    apply_structure()
    stats["parts"] = import_parts(data["parts"])
    stats["sets"] = import_sets(data["sets"])
    stats["minifigs"] = import_minifigs(data["minifigs"])
    return stats


# ---------------------------------------------------------------------------
# Rebrickable CSV folder
# ---------------------------------------------------------------------------
def _open_csv(folder: Path, name: str):
    for candidate in (folder / f"{name}.csv", folder / f"{name}.csv.gz"):
        if candidate.exists():
            if candidate.suffix == ".gz":
                return io.TextIOWrapper(gzip.open(candidate, "rb"), encoding="utf-8")
            return open(candidate, encoding="utf-8", newline="")
    return None


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@transaction.atomic
def import_rebrickable_csv(folder: Path | str) -> dict:
    folder = Path(folder)
    stats = {}
    fh = _open_csv(folder, "colors")
    if fh:
        with fh:
            rows = [(_int(r["id"]), r["name"], r.get("rgb", ""), r.get("is_trans", "") in ("t", "True", "1", "true"),
                     None) for r in csv.DictReader(fh)]
        stats["colors"] = import_colors(rows)
    fh = _open_csv(folder, "themes")
    if fh:
        with fh:
            rows = [(_int(r["id"]), r["name"], _int(r.get("parent_id"))) for r in csv.DictReader(fh)]
        stats["themes"] = import_themes(rows)
    fh = _open_csv(folder, "part_categories")
    if fh:
        with fh:
            stats["part_categories"] = import_part_categories(
                [(_int(r["id"]), r["name"]) for r in csv.DictReader(fh)])
    from .structure import apply_structure

    apply_structure()
    fh = _open_csv(folder, "parts")
    if fh:
        with fh:
            stats["parts"] = import_parts(
                [(r["part_num"], r["name"], _int(r.get("part_cat_id"))) for r in csv.DictReader(fh)])
    figs_per_set = defaultdict(int)
    inv_fh, invm_fh = _open_csv(folder, "inventories"), _open_csv(folder, "inventory_minifigs")
    if inv_fh and invm_fh:
        first = {}
        with inv_fh:
            for r in csv.DictReader(inv_fh):
                if r["set_num"] not in first or _int(r["version"], 1) < first[r["set_num"]][1]:
                    first[r["set_num"]] = (r["id"], _int(r["version"], 1))
        inv_to_set = {v[0]: k for k, v in first.items()}
        with invm_fh:
            for r in csv.DictReader(invm_fh):
                s = inv_to_set.get(r["inventory_id"])
                if s:
                    figs_per_set[s] += _int(r.get("quantity"), 1)
    fh = _open_csv(folder, "sets")
    if fh:
        with fh:
            rows = [(r["set_num"], r["name"], _int(r.get("year")), _int(r.get("theme_id")), _int(r.get("num_parts")),
                     figs_per_set.get(r["set_num"]) if figs_per_set else None, r.get("img_url", ""))
                    for r in csv.DictReader(fh)]
        stats["sets"] = import_sets(rows)
    fh = _open_csv(folder, "minifigs")
    if fh:
        with fh:
            stats["minifigs"] = import_minifigs(
                [(r["fig_num"], r["name"], _int(r.get("num_parts"))) for r in csv.DictReader(fh)])
    fh = _open_csv(folder, "elements")
    if fh:
        with fh:
            stats["elements"] = import_elements(
                [(r["element_id"], r["part_num"], _int(r["color_id"])) for r in csv.DictReader(fh)])
    return stats
