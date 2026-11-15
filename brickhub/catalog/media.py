"""Product pictures.

A listing shows the photos added in the panel; without them it shows the BrickLink catalogue picture of the
item (set, minifigure, or the part in its colour). When BrickLink has no picture, a part with an Element ID shows
the official LEGO photo of that element, and only then the neutral "Фото незабаром" placeholder.
Nothing is taken from Rebrickable.
"""
from __future__ import annotations

from django.conf import settings
from django.templatetags.static import static

from .bricklink import element_image, item_image

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


def catalogue_pictures(product) -> list[str]:
    """Pictures from the catalogues, best first: BrickLink, then the LEGO photo of the element."""
    out = []
    picture = bricklink_picture(product)
    if picture:
        out.append(picture)
    if settings.SHOP.get("BRICKLINK_IMAGES", True) and product.kind == "part":
        element = product.element_id
        if element:
            out.append(element_image(element))
    return out


def image_urls(product, large: bool = False) -> tuple[str, str]:
    """(src, fallbacks). fallbacks: space-separated pictures to try, in order, when one does not load."""
    photo = product.main_image
    if photo:
        src = photo.url if large else photo.thumb_url
        if src:
            return src, placeholder_url()
    pictures = catalogue_pictures(product)
    if pictures:
        return pictures[0], " ".join(pictures[1:] + [placeholder_url()])
    return placeholder_url(), ""


def gallery(product) -> list[dict]:
    fallback = placeholder_url()
    items = [{"src": img.url, "thumb": img.thumb_url, "alt": img.alt or product.title, "fallback": fallback}
             for img in product.images.all() if img.url]
    if not items:
        pictures = catalogue_pictures(product)
        if pictures:
            rest = " ".join(pictures[1:] + [fallback])
            items = [{"src": pictures[0], "thumb": pictures[0], "alt": product.title, "fallback": rest}]
    if not items:
        items = [{"src": fallback, "thumb": fallback, "alt": product.title, "fallback": "", "placeholder": True}]
    return items
