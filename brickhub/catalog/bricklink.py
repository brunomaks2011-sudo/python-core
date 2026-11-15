"""BrickLink: item numbers, catalogue links and catalogue pictures.

Pictures are not copied to the server: the buyer's browser loads them straight from BrickLink's image server
(the hosting may not reach BrickLink, the browser always can). When BrickLink has no picture for an item, the
page shows the neutral placeholder instead.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

IMAGES = "https://img.bricklink.com/ItemImage"
CATALOG = "https://www.bricklink.com/v2/catalog/catalogitem.page"
LEGO_ELEMENT_IMAGE = "https://www.lego.com/cdn/product-assets/element.img.lod5photo.192_192/{}.jpg"

# BrickLink item types: (picture folder, catalogue parameter)
_TYPES = {"set": ("SN", "S"), "gear": ("GN", "G"), "book": ("BN", "B"), "minifig": ("MN", "M"), "part": ("PN", "P")}


def part_number(part) -> str:
    """BrickLink number of a part: its own BrickLink number when it differs, otherwise the Design ID."""
    return ((getattr(part, "bricklink_no", "") or "").strip() or part.design_id).strip()


def part_image(number: str, bricklink_color: int | None) -> str:
    if not number or bricklink_color is None:
        return ""
    return f"{IMAGES}/PN/{bricklink_color}/{quote(number)}.png"


def element_image(element_id: str) -> str:
    return LEGO_ELEMENT_IMAGE.format(quote(element_id)) if element_id else ""


def _item(product):
    """(type, number) of the BrickLink catalogue item a listing corresponds to, or (None, "")."""
    if product.kind == "part" and product.part_id:
        return "part", part_number(product.part)
    if product.kind == "minifig" and product.minifigure_id:
        return ("minifig", product.minifigure.bricklink_id) if product.minifigure.bricklink_id else (None, "")
    if product.lego_set_id:
        number = product.lego_set.number
        if product.kind == "set":
            return "set", number
        kind = "book" if product.kind == "book" else "gear"
        return kind, number.removesuffix("-1")
    return None, ""


def item_image(product) -> str:
    kind, number = _item(product)
    if kind is None or not number:
        return ""
    if kind == "part":
        return part_image(number, product.color.bricklink_id if product.color_id else None)
    return f"{IMAGES}/{_TYPES[kind][0]}/0/{quote(number)}.png"


def catalog_url(product) -> str:
    kind, number = _item(product)
    if kind is None or not number:
        return ""
    params = {_TYPES[kind][1]: number}
    if kind == "part" and product.color_id and product.color.bricklink_id is not None:
        params["idColor"] = product.color.bricklink_id
    return f"{CATALOG}?{urlencode(params)}"
