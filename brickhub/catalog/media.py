"""Product pictures.

Only photos added by the shop owner are shown (uploaded files or links typed
in the admin panel).  Nothing is pulled in automatically: a product without a
photo gets a neutral "Фото незабаром" placeholder.
"""
from __future__ import annotations

from django.templatetags.static import static

PLACEHOLDER = "img/no-photo.svg"


def placeholder_url() -> str:
    return static(PLACEHOLDER)


def has_photo(product) -> bool:
    return product.main_image is not None


def image_urls(product, large: bool = False) -> tuple[str, str]:
    """(src, fallback). fallback replaces a photo whose link stopped working."""
    photo = product.main_image
    if photo:
        src = photo.url if large else photo.thumb_url
        if src:
            return src, placeholder_url()
    return placeholder_url(), ""


def gallery(product) -> list[dict]:
    fallback = placeholder_url()
    items = [{"src": img.url, "thumb": img.thumb_url, "alt": img.alt or product.title, "fallback": fallback}
             for img in product.images.all() if img.url]
    if not items:
        items = [{"src": fallback, "thumb": fallback, "alt": product.title, "fallback": "", "placeholder": True}]
    return items
