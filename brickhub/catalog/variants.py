"""Variants of the same LEGO item shown on the product page: other colours of a part
(colour picker) and new / used listings of the same item (condition switch)."""
from __future__ import annotations

from .models import Product


def color_variants(product) -> list[dict]:
    """One entry per colour of the same part; empty when the part has a single colour."""
    if product.kind != Product.KIND_PART or not product.part_id:
        return []
    items = list(
        Product.objects.active().filter(kind=Product.KIND_PART, part_id=product.part_id)
        .select_related("color", "inventory").order_by("color__sort_order", "color__name", "condition")
    )
    groups: dict[int, list] = {}
    for p in items:
        groups.setdefault(p.color_id, []).append(p)
    if product.color_id not in groups:  # inactive product previewed by staff
        groups[product.color_id] = [product]
    out = []
    for color_id, group in groups.items():
        if color_id == product.color_id:
            pick = product
        else:
            pick = (next((p for p in group if p.condition == product.condition and p.in_stock), None)
                    or next((p for p in group if p.in_stock), None)
                    or next((p for p in group if p.condition == product.condition), group[0]))
        color = pick.color
        out.append({
            "url": pick.get_absolute_url(),
            "name": color.display_name if color else "—",
            "official": color.name if color else "",
            "code": color.code if color else "",
            "hex": color.hex if color else "#cccccc",
            "trans": bool(color and color.is_transparent),
            "in_stock": any(p.in_stock for p in group),
            "price": pick.price,
            "current": color_id == product.color_id,
        })
    return out if len(out) > 1 else []


def condition_variants(product) -> list[dict]:
    """New / used listings of the same item; empty when only one condition is on sale."""
    qs = Product.objects.active().filter(kind=product.kind).select_related("inventory")
    if product.kind == Product.KIND_PART and product.part_id:
        qs = qs.filter(kind=Product.KIND_PART, part_id=product.part_id, color_id=product.color_id)
    elif product.minifigure_id:
        qs = qs.filter(minifigure_id=product.minifigure_id)
    elif product.lego_set_id:
        qs = qs.filter(lego_set_id=product.lego_set_id)
    else:
        return []
    by_condition: dict[str, Product] = {}
    for p in qs.order_by("-inventory__quantity", "pk"):
        by_condition.setdefault(p.condition, p)
    by_condition[product.condition] = product
    if len(by_condition) < 2:
        return []
    labels = dict(Product.CONDITIONS)
    return [{"label": labels[c], "url": by_condition[c].get_absolute_url(), "price": by_condition[c].price,
             "in_stock": by_condition[c].in_stock, "current": c == product.condition}
            for c in (Product.CONDITION_NEW, Product.CONDITION_USED) if c in by_condition]
