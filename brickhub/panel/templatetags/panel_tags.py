from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from catalog.media import catalogue_pictures
from panel.owners import owner_people

register = template.Library()


def _people(context) -> dict:
    cache = context.render_context
    if "_owner_people" not in cache:
        cache["_owner_people"] = {p["pk"]: p for p in owner_people()}
    return cache["_owner_people"]


@register.simple_tag(takes_context=True)
def owner_badge(context, owner_id):
    """Coloured label with the name of whose goods a listing is."""
    person = _people(context).get(owner_id)
    if person is None:
        return format_html('<span class="owner is-none" title="{}">{}</span>', "Власника не вказано", "не вказано")
    return format_html('<span class="owner" style="--c:{}" title="{} · {}">{}</span>', person["color"],
                       person["role"], person["email"], person["name"])


PHOTO_LABELS = {"own": ("своє фото", "badge-green"), "bricklink": ("фото з BrickLink", "badge-green"),
                "lego": ("фото з LEGO", "badge-green"), "none": ("без фото — додайте", "badge-orange")}


@register.simple_tag
def photo_badge(product, small=False):
    """What picture the site shows for a product: the owner's photo, BrickLink's, LEGO's, or none.

    Whether a BrickLink / LEGO picture exists is known only in the browser, so a product not checked yet gets a
    "перевіряю…" badge that the panel script replaces (and stores the answer)."""
    style = mark_safe(' style="height:20px"') if small else ""
    if product.main_image:
        if small:
            return ""
        text, cls = PHOTO_LABELS["own"]
        return format_html('<span class="badge {}">{}</span>', cls, text)
    pictures = catalogue_pictures(product)
    state = product.catalog_picture if pictures else "none"
    if state and state == product.catalog_picture:
        text, cls = PHOTO_LABELS[state]
        return format_html('<span class="badge {}"{}>{}</span>', cls, style, text)
    return format_html('<span class="badge"{} data-photo-check="{}" data-pictures="{}">перевіряю фото…</span>',
                       style, product.pk, " ".join(pictures))
