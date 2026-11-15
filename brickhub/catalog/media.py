"""Product pictures.

A listing shows the photos added in the panel; without them it shows the BrickLink catalogue picture of the
item (set, minifigure, or the part in its colour). If BrickLink has no picture either, a neutral
"Фото незабаром" placeholder is shown.
"""
from __future__ import annotations

from django.conf import settings
from django.templatetags.static import static

from .bricklink import item_image

PLACEHOLDER = "img/no-photo.svg"


def placeholder_url() -> str:
    return static(PLACEHOLDER)


def has_photo(product) -> bool:
    """A photo added in the panel (uploaded or linked)."""
    return product.main_image is not None


def bricklink_picture(product) -> str:
    if not settings.SHOP.get("BRICKLINK_IMAGES", True):
        return ""
    return item_image(product)


def image_urls(product, large: bool = False) -> tuple[str, str]:
    """(src, fallback). fallback replaces a picture that does not load."""
    photo = product.main_image
    if photo:
        src = photo.url if large else photo.thumb_url
        if src:
            return src, placeholder_url()
    picture = bricklink_picture(product)
    if picture:
        return picture, placeholder_url()
    return placeholder_url(), ""


def gallery(product) -> list[dict]:
    fallback = placeholder_url()
    items = [{"src": img.url, "thumb": img.thumb_url, "alt": img.alt or product.title, "fallback": fallback}
             for img in product.images.all() if img.url]
    if not items:
        picture = bricklink_picture(product)
        if picture:
            items = [{"src": picture, "thumb": picture, "alt": product.title, "fallback": fallback}]
    if not items:
        items = [{"src": fallback, "thumb": fallback, "alt": product.title, "fallback": "", "placeholder": True}]
    return items
