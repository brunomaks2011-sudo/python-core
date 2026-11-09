from __future__ import annotations

import json
from urllib.parse import urlencode

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from catalog.media import image_urls
from core.utils import format_uah, plural_uk

register = template.Library()


@register.filter
def uah(value):
    return format_uah(value)


@register.filter
def plural(value, forms: str):
    """{{ n|plural:"деталь,деталі,деталей" }}"""
    one, few, many = (forms.split(",") + ["", "", ""])[:3]
    try:
        return plural_uk(int(value), one, few, many)
    except (TypeError, ValueError):
        return many


@register.filter
def thousands(value):
    try:
        return f"{int(value):,}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return value


@register.simple_tag
def product_img(product, size: str = "card", eager: bool = False, cls: str = ""):
    src, fallback = image_urls(product, large=size == "large")
    dim = {"card": 320, "large": 720, "thumb": 96, "mini": 64}.get(size, 320)
    attrs = {
        "src": src,
        "alt": product.title,
        "width": dim,
        "height": dim,
        "loading": "eager" if eager else "lazy",
        "decoding": "async",
        "class": f"pimg {cls}".strip(),
    }
    if fallback:
        attrs["data-fallback"] = fallback
    if eager:
        attrs["fetchpriority"] = "high"
    html = " ".join(format_html('{}="{}"', k, v) for k, v in attrs.items())
    return mark_safe(f"<img {html}>")


@register.simple_tag(takes_context=True)
def toggle_param(context, name: str, value: str):
    """URL that toggles ``value`` in the multi-value GET parameter ``name``."""
    request = context["request"]
    params = request.GET.copy()
    values = params.getlist(name)
    if value in values:
        values.remove(value)
    else:
        values.append(value)
    params.setlist(name, values)
    params.pop("page", None)
    query = params.urlencode()
    return f"?{query}" if query else "?"


@register.simple_tag(takes_context=True)
def set_param(context, name: str, value):
    request = context["request"]
    params = request.GET.copy()
    if value in (None, ""):
        params.pop(name, None)
    else:
        params[name] = value
    params.pop("page", None)
    query = params.urlencode()
    return f"?{query}" if query else "?"


@register.filter
def in_list(value, values):
    return value in (values or [])


@register.filter
def stars(rating):
    try:
        r = float(rating)
    except (TypeError, ValueError):
        r = 0
    full = int(r + 0.25)
    return "★" * full + "☆" * (5 - full)


@register.filter
def jsonld(data):
    return mark_safe(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


@register.simple_tag
def qs(**kwargs):
    return urlencode({k: v for k, v in kwargs.items() if v not in (None, "")})


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


# category icon = a drawing of a typical part (Design ID, Rebrickable colour id) ...
CATEGORY_ICONS = {
    "tsehlynky": ("3001", 4), "skosy": ("3039", 25), "arky-ta-vyhnuti-tsehlynky": ("3659", 19),
    "plastyny": ("3020", 1), "plytky": ("3068b", 14), "paneli": ("87552", 71), "kolesa-ta-shyny": ("55981", 71),
    "vikna-ta-dveri": ("60592", 15), "kryla": ("43722", 72), "sharniry-ta-povorotni-platformy": ("3937", 72),
    "shesterni": ("3648b", 71), "elementy-technic": ("32524", 0), "prozori-detali": ("3062b", 36),
    "roslyny": ("24866", 10), "aksesuary-dlia-fihurok": ("64567", 71), "ohorozhi-drabyny-ta-opory": ("3633", 70),
    "duplo": ("3437", 322), "inshi-elementy": ("87087", 72), "detali": ("3003", 4),
}
_color_pk_cache: dict[int, tuple[int, str]] = {}


@register.simple_tag
def part_icon(design_id: str, rb_color: int) -> str:
    from django.urls import reverse

    from catalog.models import Color

    if rb_color not in _color_pk_cache:
        c = Color.objects.filter(rebrickable_id=rb_color).only("pk", "rgb").first()
        if not c:
            return ""
        _color_pk_cache[rb_color] = (c.pk, c.rgb)
    pk, rgb = _color_pk_cache[rb_color]
    return reverse("catalog:part_svg", args=[design_id, pk]) + f"?v={rgb}"


# ... or a flat illustration from static/img/categories/<slug>.svg
STATIC_CATEGORY_ICONS = {slug: f"img/categories/{slug}.svg" for slug in (
    "tvaryny", "bazovi-plastyny", "dlia-transportu", "elektronika", "chastyny-minifihurok",
    "volossia-ta-holovni-ubory", "zbroia-ta-instrumenty", "kontejnery-ta-yashchyky", "trubky-shlanhy-ta-nytky",
    "prapory-ta-znaky", "nalipky",
    # accessories
    "zberihannia", "vitryny-ta-pidstavky", "osvitlennia", "separatory-ta-instrumenty", "kantseliariia",
    "sumky-ta-riukzaky", "odiah", "hodynnyky", "mahnity", "ihry-ta-pazly", "dekor-i-suveniry", "inshi-aksesuary",
)}


@register.simple_tag
def category_icon(slug: str) -> str:
    if slug in STATIC_CATEGORY_ICONS:
        from django.templatetags.static import static

        return static(STATIC_CATEGORY_ICONS[slug])
    design, color = CATEGORY_ICONS.get(slug, ("3003", 4))
    return part_icon(design, color)


@register.simple_tag(takes_context=True)
def page_link(context, number):
    params = context["request"].GET.copy()
    if int(number) <= 1:
        params.pop("page", None)
    else:
        params["page"] = number
    query = params.urlencode()
    return f"?{query}" if query else context["request"].path


@register.simple_tag
def gallery_items(product):
    from catalog.media import gallery

    return gallery(product)
