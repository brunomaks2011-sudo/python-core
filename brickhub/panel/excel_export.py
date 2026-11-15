"""All products in one Excel table a person can read: what is on sale, with both numberings, colour, stock and price.

Used by the panel's "Експорт Excel" button, by `manage.py export_products`, and by `manage.py clear_products`,
which saves this table before it deletes anything.
"""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone

from catalog.models import Product

COLUMNS = [
    ("Артикул", 18), ("Назва", 46), ("Тип", 12), ("Design ID (LEGO)", 16), ("Element ID (LEGO)", 17),
    ("Номер BrickLink", 18), ("Номер набору / фігурки", 20), ("Колір", 26), ("Колір BrickLink", 10),
    ("Стан", 10), ("Кількість", 10), ("Ціна, ₴", 11), ("Стара ціна, ₴", 12), ("Місце на складі", 15),
    ("Категорія", 30), ("Серія", 24), ("Чий товар", 22), ("На сайті", 9), ("Продано", 9),
]
EXPORT_DIR = Path(settings.BASE_DIR) / "exports"


def _row(p: Product) -> list:
    inv = getattr(p, "inventory", None)
    number = ""
    if p.lego_set_id:
        number = p.lego_set.base_number
    elif p.minifigure_id:
        number = p.minifigure.bricklink_id or p.minifigure.fig_number
    owner = ""
    if p.owner_id:
        owner = p.owner.get_full_name() or p.owner.email
    return [
        p.sku, p.title, p.get_kind_display(),
        p.lego_design_id, p.element_id, p.bricklink_number if p.kind == Product.KIND_PART else "",
        number,
        (f"{p.color.display_name} ({p.color.name})" if p.color.display_name != p.color.name else p.color.name)
        if p.color_id else "",
        p.color.bricklink_id if p.color_id and p.color.bricklink_id is not None else "",
        p.get_condition_display(), inv.quantity if inv else 0,
        p.price, p.old_price or None, inv.location if inv else "",
        p.category.name if p.category_id else "", ", ".join(t.display_name for t in p.themes),
        owner, "так" if p.is_active else "ні", p.sold_count,
    ]


def products_workbook(qs=None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    if qs is None:
        qs = Product.objects.all()
    qs = qs.with_related().select_related("owner").order_by("kind", "title", "sku")
    wb = Workbook()
    ws = wb.active
    ws.title = "Товари"
    ws.append([name for name, _ in COLUMNS])
    for i, (_, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="D01012")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    count = 0
    for p in qs.iterator(chunk_size=500):
        ws.append(_row(p))
        count += 1
    for col in ("L", "M"):  # prices
        for cell in ws[col][1:]:
            cell.number_format = "0.00"
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    totals = qs.order_by().aggregate(units=Sum("inventory__quantity"),
                                     value=Sum(F("inventory__quantity") * F("price")))
    summary = wb.create_sheet("Підсумок")
    summary.append(["Збережено", timezone.localtime().strftime("%d.%m.%Y %H:%M")])
    summary.append(["Товарів", count])
    summary.append(["Одиниць на складі", totals["units"] or 0])
    summary.append(["На суму, ₴", totals["value"] or Decimal("0")])
    summary["B4"].number_format = "0.00"
    for label, kind_name in Product.KINDS:
        n = qs.filter(kind=label).count()
        if n:
            summary.append([f"— {kind_name}", n])
    summary.column_dimensions["A"].width = 24
    summary.column_dimensions["B"].width = 18
    for row in summary.iter_rows(min_col=1, max_col=1):
        row[0].font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def save_products_workbook(path: Path | str | None = None) -> tuple[Path, int]:
    """Write the table to a file (default exports/tovary-<date>.xlsx). Returns (path, number of products)."""
    path = Path(path) if path else EXPORT_DIR / f"tovary-{timezone.localtime():%Y-%m-%d-%H%M%S}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    count = Product.objects.count()
    path.write_bytes(products_workbook())
    return path, count
