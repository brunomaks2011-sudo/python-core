"""Which picture to show for a product (uploaded photo → catalogue photo → generated illustration)."""
from __future__ import annotations

from django.urls import reverse


def generated_url(product) -> str:
    if product.kind == "part" and product.part_id and product.color_id:
        return reverse("catalog:part_svg", args=[product.part.design_id, product.color_id]) + f"?v={product.color.rgb}"
    accent = (product.theme.accent if product.theme_id else "#E3000B").lstrip("#")
    if product.kind == "minifig":
        return reverse("catalog:fig_svg", args=[accent])
    number = product.official_number or product.sku
    return reverse("catalog:set_svg", args=[number.replace("/", "-")[:30] or "lego", accent])


def image_urls(product, large: bool = False) -> tuple[str, str]:
    """(src, fallback). fallback is used by JS when an external photo fails to load."""
    fallback = generated_url(product)
    photo = product.main_image
    if photo:
        src = photo.url if large else photo.thumb_url
        if src:
            return src, fallback
    return fallback, ""


def gallery(product) -> list[dict]:
    fallback = generated_url(product)
    items = [{"src": img.url, "thumb": img.thumb_url, "alt": img.alt or product.title, "fallback": fallback}
             for img in product.images.all() if img.url]
    if not items:
        items = [{"src": fallback, "thumb": fallback, "alt": product.title, "fallback": ""}]
    return items
