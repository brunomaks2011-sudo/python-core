"""Bulk import of products from CSV / XLSX.

Designed for thousands of rows: reference data is preloaded, new rows go in
with bulk_create and existing rows with bulk_update.  Every LEGO number is
checked against the reference catalogue – unknown numbers are reported as
errors instead of being silently created (unless the admin explicitly allows
creating catalogue entries and the row contains an official name).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Category, Color, Element, Inventory, InventoryMovement, LegoSet, Minifigure, Part, Product, ProductImage,
    StockNotification, Theme,
)
from core.utils import make_slug

# header aliases (lower-case) -> canonical field
ALIASES = {
    "design_id": ["design_id", "design id", "part", "part_num", "part number", "номер деталі", "деталь", "itemid",
                  "item no", "item_no"],
    "element_id": ["element_id", "element id", "елемент", "номер елемента"],
    "color": ["color", "colour", "колір", "color_name", "назва кольору"],
    "color_id": ["color_id", "colour_id", "bricklink color", "bl_color", "номер кольору", "colorid"],
    "set_number": ["set_number", "set", "set_num", "set number", "номер набору", "набір"],
    "fig_number": ["fig_number", "minifig", "fig", "fig_num", "номер фігурки", "мініфігурка", "bricklink_id"],
    "sku": ["sku", "артикул", "артикул магазину"],
    "condition": ["condition", "стан", "new/used"],
    "quantity": ["quantity", "qty", "кількість", "залишок", "stock"],
    "price": ["price", "ціна", "ціна, грн", "price_uah", "ціна за шт"],
    "old_price": ["old_price", "стара ціна", "compare_at_price"],
    "location": ["location", "місце", "місце на складі", "remarks"],
    "title": ["title", "назва", "name"],
    "name_uk": ["name_uk", "назва українською"],
    "official_name": ["official_name", "офіційна назва"],
    "category": ["category", "категорія"],
    "theme": ["theme", "серія"],
    "description": ["description", "опис"],
    "completeness": ["completeness", "комплектація"],
    "image_url": ["image_url", "image", "фото", "зображення"],
    "active": ["active", "активний", "is_active"],
    "year": ["year", "рік"],
    "pieces": ["pieces", "деталей", "кількість деталей"],
    "age": ["age", "вік"],
    "is_new": ["is_new", "новинка"],
    "is_rare": ["is_rare", "рідкісний"],
    "is_featured": ["is_featured", "популярний"],
    "is_bestseller": ["is_bestseller", "хіт"],
}
LOOKUP = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}

TEMPLATES = {
    "parts": ["design_id", "color_id", "color", "element_id", "condition", "quantity", "price", "location", "name_uk"],
    "sets": ["set_number", "condition", "quantity", "price", "old_price", "completeness", "age", "description",
             "image_url", "is_new", "is_rare"],
    "minifigs": ["fig_number", "condition", "quantity", "price", "completeness", "image_url"],
    "stock": ["sku", "quantity", "price", "old_price", "active"],
}
TEMPLATE_EXAMPLES = {
    "parts": [["3001", "5", "Red", "", "new", "250", "6.00", "A-01-03", "Цеглинка 2 × 4"],
              ["3023", "11", "Black", "", "new", "1200", "2.00", "A-02-11", ""],
              ["3069b", "", "Trans-Clear", "", "used", "40", "1.50", "B-07-01", ""]],
    "sets": [["75355", "new", "3", "8999", "", "", "18", "", "", "yes", ""],
             ["42143-1", "used", "1", "11999", "", "Повний комплект, без коробки", "18", "", "", "", "yes"]],
    "minifigs": [["fig-002057", "new", "2", "389", "", ""]],
    "stock": [["BH-P-3001-5-N", "300", "6.50", "", "yes"]],
}

MAX_ROWS = 50000


class ImportFileError(Exception):
    pass


@dataclass
class RowResult:
    line: int
    status: str  # created / updated / skipped / error
    message: str = ""
    sku: str = ""


@dataclass
class ImportReport:
    kind: str
    dry_run: bool
    total: int = 0
    created: int = 0
    updated: int = 0
    errors: int = 0
    skipped: int = 0
    rows: list = field(default_factory=list)

    def add(self, res: RowResult):
        self.rows.append(res)
        if res.status == "error":
            self.errors += 1
        elif res.status == "created":
            self.created += 1
        elif res.status == "updated":
            self.updated += 1
        else:
            self.skipped += 1

    @property
    def error_rows(self):
        return [r for r in self.rows if r.status == "error"]


# ---------------------------------------------------------------------------
# file reading
# ---------------------------------------------------------------------------
def read_table(uploaded) -> list[dict]:
    name = (getattr(uploaded, "name", "") or "").lower()
    raw = uploaded.read()
    if name.endswith((".xlsx", ".xlsm")):
        return _read_xlsx(raw)
    if name.endswith(".xls"):
        raise ImportFileError("Старий формат .xls не підтримується — збережіть файл як .xlsx або .csv")
    return _read_csv(raw)


def _normalize_header(h) -> str:
    key = str(h or "").strip().lower().replace("\ufeff", "")
    return LOOKUP.get(key, key)


def _read_csv(raw: bytes) -> list[dict]:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportFileError("Не вдалося прочитати кодування файлу (підтримуються UTF-8 та Windows-1251)")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        raise ImportFileError("Файл порожній")
    headers = [_normalize_header(h) for h in rows[0]]
    out = []
    for values in rows[1:MAX_ROWS + 1]:
        if not any(str(v).strip() for v in values):
            continue
        out.append({headers[i]: (values[i].strip() if i < len(values) else "") for i in range(len(headers))})
    return out


def _read_xlsx(raw: bytes) -> list[dict]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise ImportFileError("Не вдалося відкрити Excel-файл") from exc
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        headers = [_normalize_header(h) for h in next(it)]
    except StopIteration:
        raise ImportFileError("Файл порожній")
    out = []
    for i, values in enumerate(it):
        if i >= MAX_ROWS:
            break
        if not values or not any(v not in (None, "") for v in values):
            continue
        row = {}
        for j, h in enumerate(headers):
            v = values[j] if j < len(values) else None
            if isinstance(v, float) and v.is_integer() and h not in ("price", "old_price"):
                v = int(v)
            row[h] = "" if v is None else str(v).strip()
        out.append(row)
    wb.close()
    return out


def detect_kind(rows: list[dict]) -> str:
    keys = set(rows[0]) if rows else set()
    if "design_id" in keys or "element_id" in keys:
        return "parts"
    if "set_number" in keys:
        return "sets"
    if "fig_number" in keys:
        return "minifigs"
    if "sku" in keys:
        return "stock"
    raise ImportFileError("Не вдалося визначити тип файлу — потрібна колонка design_id, set_number, fig_number або sku")


# ---------------------------------------------------------------------------
# value parsing
# ---------------------------------------------------------------------------
def _price(v):
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v).replace("₴", "").replace("грн", "").replace(" ", "").replace("\u202f", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"ціна «{v}» не є числом")
    if d < 0:
        raise ValueError("ціна не може бути від'ємною")
    return d.quantize(Decimal("0.01"))


def _qty(v):
    if v in (None, ""):
        return None
    try:
        q = int(Decimal(str(v).replace(" ", "").replace(",", ".")))
    except InvalidOperation:
        raise ValueError(f"кількість «{v}» не є цілим числом")
    if q < 0:
        raise ValueError("кількість не може бути від'ємною")
    return q


def _cond(v):
    s = str(v or "new").strip().lower()
    if s in ("", "n", "new", "новий", "нова", "нове", "н"):
        return "new"
    if s in ("u", "used", "б/у", "бу", "вживаний", "вживана", "б/в"):
        return "used"
    raise ValueError(f"невідомий стан «{v}» (new / used)")


def _bool(v):
    return str(v or "").strip().lower() in ("1", "yes", "y", "true", "так", "+", "да")


class ColorResolver:
    def __init__(self):
        self.by_bl, self.by_name, self.by_rb = {}, {}, {}
        for c in Color.objects.all():
            if c.bricklink_id is not None:
                self.by_bl[c.bricklink_id] = c
            if c.rebrickable_id is not None:
                self.by_rb[c.rebrickable_id] = c
            for n in (c.name, c.name_uk, c.lego_name):
                if n:
                    self.by_name.setdefault(n.lower(), c)

    def get(self, color_id: str, color: str):
        if color_id:
            cid = str(color_id).strip()
            if cid.upper().startswith("RB") and cid[2:].lstrip("-").isdigit():
                return self.by_rb.get(int(cid[2:]))
            if cid.isdigit():
                return self.by_bl.get(int(cid))
        if color:
            return self.by_name.get(str(color).strip().lower())
        return None


# ---------------------------------------------------------------------------
# importers
# ---------------------------------------------------------------------------
def run_import(rows: list[dict], kind: str, *, dry_run: bool, user=None, allow_new_catalog=False) -> ImportReport:
    if kind == "auto":
        kind = detect_kind(rows)
    report = ImportReport(kind=kind, dry_run=dry_run, total=len(rows))
    func = {"parts": _import_parts, "sets": _import_sets, "minifigs": _import_minifigs, "stock": _import_stock}[kind]
    try:
        with transaction.atomic():
            restocked = func(rows, report, user=user, allow_new_catalog=allow_new_catalog)
            if dry_run:
                transaction.set_rollback(True)
            elif restocked:
                _queue_notifications(restocked)
    except ImportFileError:
        raise
    return report


def _queue_notifications(product_ids):
    from catalog.notifications import notify_back_in_stock

    pending = set(StockNotification.objects.filter(product_id__in=list(product_ids), notified_at__isnull=True)
                  .values_list("product_id", flat=True))
    for pid in pending:
        transaction.on_commit(lambda pid=pid: notify_back_in_stock(pid))


class _Unique:
    """Generates unique SKUs / slugs in memory for bulk inserts."""

    def __init__(self):
        self.skus = set(Product.objects.values_list("sku", flat=True))
        self.slugs = set(Product.objects.values_list("slug", flat=True))

    def take(self, pool: set, base: str) -> str:
        value, n = base, 2
        while value in pool:
            value, n = f"{base}-{n}", n + 1
        pool.add(value)
        return value


def _import_parts(rows, report, user=None, allow_new_catalog=False):
    colors = ColorResolver()
    design_ids = {str(r.get("design_id", "")).strip() for r in rows if r.get("design_id")}
    element_ids = {str(r.get("element_id", "")).strip() for r in rows if r.get("element_id")}
    parts = {}
    ids = list(design_ids)
    for i in range(0, len(ids), 900):
        for p in Part.objects.filter(design_id__in=ids[i:i + 900]).select_related("category"):
            parts[p.design_id.lower()] = p
    elements = {}
    el_ids = list(element_ids)
    for i in range(0, len(el_ids), 900):
        for e in Element.objects.filter(element_id__in=el_ids[i:i + 900]).select_related("part", "color"):
            elements[e.element_id] = e
    categories = {c.slug: c for c in Category.objects.filter(kind="part")}
    cat_by_name = {c.name.lower(): c for c in categories.values()}
    fallback_cat = categories.get("inshi-elementy")
    existing = {}
    part_pks = [p.pk for p in parts.values()] + [e.part_id for e in elements.values()]
    for i in range(0, len(part_pks), 900):
        for prod in Product.objects.filter(kind="part", part_id__in=part_pks[i:i + 900]).select_related("inventory"):
            existing[(prod.part_id, prod.color_id, prod.condition)] = prod
    uniq = _Unique()
    now = timezone.now()
    to_create, to_update, inv_updates, movements, images, new_elements = [], [], [], [], [], []
    restocked = set()
    seen_keys = set()
    for n, row in enumerate(rows, start=2):
        try:
            design = str(row.get("design_id", "")).strip()
            el_id = str(row.get("element_id", "")).strip()
            part = parts.get(design.lower()) if design else None
            color = colors.get(row.get("color_id", ""), row.get("color", ""))
            if el_id and el_id in elements:
                el = elements[el_id]
                part = part or el.part
                color = color or el.color
                if el.part_id != part.pk or el.color_id != color.pk:
                    raise ValueError(f"Element ID {el_id} належить деталі {el.part.design_id} ({el.color.name})")
            if not design and not part:
                raise ValueError("не вказано design_id")
            if part is None:
                official = (row.get("official_name") or "").strip()
                if allow_new_catalog and official:
                    part = Part.objects.create(design_id=design, name=official, name_uk=row.get("name_uk", ""),
                                               category=fallback_cat)
                    parts[design.lower()] = part
                else:
                    raise ValueError(f"деталі {design} немає в каталозі LEGO (перевірте номер)")
            if color is None:
                raise ValueError(f"колір «{row.get('color_id') or row.get('color') or '—'}» не знайдено")
            cond = _cond(row.get("condition"))
            qty = _qty(row.get("quantity"))
            price = _price(row.get("price"))
            old_price = _price(row.get("old_price"))
            key = (part.pk, color.pk, cond)
            if key in seen_keys:
                raise ValueError("рядок дублює попередній (та сама деталь, колір і стан)")
            seen_keys.add(key)
            if row.get("name_uk") and row["name_uk"] != part.name_uk:
                part.name_uk = row["name_uk"]
                part.save(update_fields=["name_uk"])
            if el_id and el_id not in elements:
                new_elements.append(Element(element_id=el_id, part=part, color=color))
                elements[el_id] = new_elements[-1]
            category = None
            if row.get("category"):
                category = categories.get(row["category"].strip()) or cat_by_name.get(row["category"].strip().lower())
            prod = existing.get(key)
            if prod:
                changed = False
                if price is not None and price != prod.price:
                    prod.price = price
                    changed = True
                if row.get("old_price") is not None and "old_price" in row:
                    prod.old_price = old_price
                    changed = True
                if row.get("title"):
                    prod.title = row["title"][:255]
                    changed = True
                if category:
                    prod.category = category
                    changed = True
                if row.get("active", "") != "":
                    prod.is_active = _bool(row["active"])
                    changed = True
                if changed:
                    prod.updated_at = now
                    to_update.append(prod)
                inv = prod.inventory
                if qty is not None and qty != inv.quantity:
                    if inv.quantity == 0 and qty > 0:
                        restocked.add(prod.pk)
                    movements.append(InventoryMovement(inventory=inv, change=qty - inv.quantity, quantity_after=qty,
                                                       reason="import", user=user))
                    inv.quantity = qty
                    inv.updated_at = now
                    if row.get("location"):
                        inv.location = row["location"][:64]
                    inv_updates.append(inv)
                elif row.get("location") and row["location"] != inv.location:
                    inv.location = row["location"][:64]
                    inv_updates.append(inv)
                report.add(RowResult(n, "updated", sku=prod.sku))
            else:
                if price is None:
                    raise ValueError("для нового товару потрібна ціна")
                prod = Product(kind="part", part=part, color=color, condition=cond, price=price, old_price=old_price,
                               category=category or part.category or fallback_cat, created_at=now,
                               is_active=_bool(row["active"]) if row.get("active", "") != "" else True)
                prod.title = (row.get("title") or part.display_name)[:255]
                base_sku = f"BH-P-{part.design_id}-{color.code}-{'U' if cond == 'used' else 'N'}".upper()
                prod.sku = uniq.take(uniq.skus, base_sku)
                prod.slug = uniq.take(uniq.slugs, make_slug(part.design_id, part.name, color.name,
                                                            "vzhyvanyi" if cond == "used" else "", max_length=180))
                prod.search_text = " ".join(filter(None, [
                    prod.sku, prod.title, "Деталь", part.design_id, part.name, part.name_uk,
                    part.alternate_ids.replace(",", " "), el_id, color.name, color.name_uk,
                    prod.category.name if prod.category else ""])).lower()
                prod._qty = qty or 0
                prod._location = (row.get("location") or "")[:64]
                prod._image = (row.get("image_url") or "").strip()
                to_create.append(prod)
                existing[key] = prod
                report.add(RowResult(n, "created", sku=prod.sku))
        except ValueError as exc:
            report.add(RowResult(n, "error", str(exc)))
    if new_elements:
        Element.objects.bulk_create(new_elements, ignore_conflicts=True)
    if to_create:
        Product.objects.bulk_create(to_create, batch_size=500)
        new_skus = [p.sku for p in to_create]
        created = {}
        for i in range(0, len(new_skus), 900):
            created.update({p.sku: p for p in Product.objects.filter(sku__in=new_skus[i:i + 900])})
        invs = []
        for p in to_create:
            pk = created[p.sku].pk
            invs.append(Inventory(product_id=pk, quantity=p._qty, location=p._location))
            if p._image:
                images.append(ProductImage(product_id=pk, external_url=p._image[:500], alt=p.title))
        Inventory.objects.bulk_create(invs, batch_size=500)
        new_ids = [created[p.sku].pk for p in to_create]
        new_invs = {}
        for i in range(0, len(new_ids), 900):
            new_invs.update({inv.product_id: inv for inv in Inventory.objects.filter(product_id__in=new_ids[i:i + 900])})
        for p in to_create:
            inv = new_invs[created[p.sku].pk]
            if inv.quantity:
                movements.append(InventoryMovement(inventory=inv, change=inv.quantity, quantity_after=inv.quantity,
                                                   reason="import", user=user))
    if to_update:
        Product.objects.bulk_update(to_update, ["price", "old_price", "title", "category", "is_active", "updated_at"],
                                    batch_size=500)
    if inv_updates:
        Inventory.objects.bulk_update(inv_updates, ["quantity", "location", "updated_at"], batch_size=500)
    if movements:
        InventoryMovement.objects.bulk_create(movements, batch_size=500)
    if images:
        ProductImage.objects.bulk_create(images, batch_size=500)
    return restocked


def _apply_common(prod, row, *, is_new_product):
    price = _price(row.get("price"))
    if price is not None:
        prod.price = price
    elif is_new_product:
        raise ValueError("для нового товару потрібна ціна")
    if "old_price" in row:
        prod.old_price = _price(row.get("old_price"))
    for attr in ("completeness", "description"):
        if row.get(attr):
            setattr(prod, attr, row[attr])
    if row.get("title"):
        prod.title = row["title"][:255]
    for flag in ("is_new", "is_rare", "is_featured", "is_bestseller"):
        if row.get(flag, "") != "":
            setattr(prod, flag, _bool(row[flag]))
    if row.get("active", "") != "":
        prod.is_active = _bool(row["active"])


def _set_stock(prod, qty, location, user, restocked):
    inv, _ = Inventory.objects.get_or_create(product=prod)
    changed = False
    if qty is not None and qty != inv.quantity:
        if inv.quantity == 0 and qty > 0:
            restocked.add(prod.pk)
        InventoryMovement.objects.create(inventory=inv, change=qty - inv.quantity, quantity_after=qty,
                                         reason="import", user=user)
        inv.quantity = qty
        changed = True
    if location and location != inv.location:
        inv.location = location[:64]
        changed = True
    if changed:
        Inventory.objects.filter(pk=inv.pk).update(quantity=inv.quantity, location=inv.location,
                                                   updated_at=timezone.now())


def _import_sets(rows, report, user=None, allow_new_catalog=False):
    restocked = set()
    cat = Category.objects.filter(slug="nabory").first()
    for n, row in enumerate(rows, start=2):
        try:
            number = str(row.get("set_number", "")).strip()
            if not number:
                raise ValueError("не вказано set_number")
            full = number if "-" in number else f"{number}-1"
            lego_set = LegoSet.objects.filter(number__iexact=full).select_related("theme").first()
            if lego_set is None:
                official = (row.get("official_name") or "").strip()
                if not (allow_new_catalog and official):
                    raise ValueError(f"набору {number} немає в каталозі LEGO (перевірте номер)")
                theme = Theme.objects.filter(slug=row.get("theme", "")).first()
                lego_set = LegoSet.objects.create(number=full, name=official, theme=theme,
                                                  year=_qty(row.get("year")), pieces=_qty(row.get("pieces")))
            if row.get("age"):
                lego_set.age_min = _qty(str(row["age"]).replace("+", ""))
                lego_set.save(update_fields=["age_min"])
            cond = _cond(row.get("condition"))
            prod = Product.objects.filter(kind="set", lego_set=lego_set, condition=cond).order_by("pk").first()
            is_new = prod is None
            if is_new:
                prod = Product(kind="set", lego_set=lego_set, condition=cond, category=cat)
            _apply_common(prod, row, is_new_product=is_new)
            prod.save()
            if row.get("image_url") and not prod.images.exists():
                ProductImage.objects.create(product=prod, external_url=row["image_url"][:500], alt=prod.title)
            _set_stock(prod, _qty(row.get("quantity")), row.get("location", ""), user, restocked)
            report.add(RowResult(n, "created" if is_new else "updated", sku=prod.sku))
        except ValueError as exc:
            report.add(RowResult(n, "error", str(exc)))
    return restocked


def _import_minifigs(rows, report, user=None, allow_new_catalog=False):
    restocked = set()
    cat = Category.objects.filter(slug="minifihurky").first()
    for n, row in enumerate(rows, start=2):
        try:
            number = str(row.get("fig_number", "")).strip()
            if not number:
                raise ValueError("не вказано fig_number")
            fig = (Minifigure.objects.filter(fig_number__iexact=number).first()
                   or Minifigure.objects.filter(bricklink_id__iexact=number).first())
            if fig is None:
                official = (row.get("official_name") or "").strip()
                if not (allow_new_catalog and official):
                    raise ValueError(f"мініфігурки {number} немає в каталозі (перевірте номер)")
                fig = Minifigure.objects.create(fig_number=number, bricklink_id=number if not number.startswith(
                    "fig-") else "", name=official, theme=Theme.objects.filter(slug=row.get("theme", "")).first())
            cond = _cond(row.get("condition"))
            prod = Product.objects.filter(kind="minifig", minifigure=fig, condition=cond).order_by("pk").first()
            is_new = prod is None
            if is_new:
                prod = Product(kind="minifig", minifigure=fig, condition=cond, category=cat)
            _apply_common(prod, row, is_new_product=is_new)
            prod.save()
            if row.get("image_url") and not prod.images.exists():
                ProductImage.objects.create(product=prod, external_url=row["image_url"][:500], alt=prod.title)
            _set_stock(prod, _qty(row.get("quantity")), row.get("location", ""), user, restocked)
            report.add(RowResult(n, "created" if is_new else "updated", sku=prod.sku))
        except ValueError as exc:
            report.add(RowResult(n, "error", str(exc)))
    return restocked


def _import_stock(rows, report, user=None, allow_new_catalog=False):
    restocked = set()
    skus = [str(r.get("sku", "")).strip().upper() for r in rows if r.get("sku")]
    products = {}
    for i in range(0, len(skus), 900):
        for p in Product.objects.filter(sku__in=skus[i:i + 900]).select_related("inventory"):
            products[p.sku.upper()] = p
    to_update, inv_updates, movements = [], [], []
    now = timezone.now()
    for n, row in enumerate(rows, start=2):
        try:
            sku = str(row.get("sku", "")).strip().upper()
            prod = products.get(sku)
            if not prod:
                raise ValueError(f"товар з артикулом {sku or '—'} не знайдено")
            price = _price(row.get("price"))
            qty = _qty(row.get("quantity"))
            changed = False
            if price is not None and price != prod.price:
                prod.price = price
                changed = True
            if "old_price" in row and row.get("old_price", "") != "":
                prod.old_price = _price(row["old_price"])
                changed = True
            if row.get("active", "") != "":
                prod.is_active = _bool(row["active"])
                changed = True
            if changed:
                prod.updated_at = now
                to_update.append(prod)
            inv = prod.inventory
            if qty is not None and qty != inv.quantity:
                if inv.quantity == 0 and qty > 0:
                    restocked.add(prod.pk)
                movements.append(InventoryMovement(inventory=inv, change=qty - inv.quantity, quantity_after=qty,
                                                   reason="import", user=user))
                inv.quantity = qty
                inv.updated_at = now
                inv_updates.append(inv)
            report.add(RowResult(n, "updated" if (changed or qty is not None) else "skipped", sku=prod.sku))
        except ValueError as exc:
            report.add(RowResult(n, "error", str(exc)))
    if to_update:
        Product.objects.bulk_update(to_update, ["price", "old_price", "is_active", "updated_at"], batch_size=500)
    if inv_updates:
        Inventory.objects.bulk_update(inv_updates, ["quantity", "updated_at"], batch_size=500)
    if movements:
        InventoryMovement.objects.bulk_create(movements, batch_size=500)
    return restocked


# ---------------------------------------------------------------------------
# templates & export
# ---------------------------------------------------------------------------
def template_xlsx(kind: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = kind
    ws.append(TEMPLATES[kind])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="D01012")
    for example in TEMPLATE_EXAMPLES[kind]:
        ws.append(example)
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


EXPORT_HEADERS = ["sku", "kind", "design_id", "color_id", "color", "set_number", "fig_number", "condition",
                  "quantity", "price", "old_price", "location", "title", "active"]


def export_rows(qs):
    yield EXPORT_HEADERS
    for p in qs.select_related("part", "color", "lego_set", "minifigure", "inventory").iterator(chunk_size=1000):
        inv = getattr(p, "inventory", None)
        yield [
            p.sku, p.kind, p.part.design_id if p.part_id else "",
            (p.color.bricklink_id if p.color_id and p.color.bricklink_id is not None else ""),
            p.color.name if p.color_id else "", p.lego_set.number if p.lego_set_id else "",
            p.minifigure.fig_number if p.minifigure_id else "", p.condition, inv.quantity if inv else 0,
            f"{p.price:.2f}", f"{p.old_price:.2f}" if p.old_price else "", inv.location if inv else "", p.title,
            "yes" if p.is_active else "no",
        ]
