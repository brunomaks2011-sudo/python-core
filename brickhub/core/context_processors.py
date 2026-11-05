from django.conf import settings
from django.core.cache import cache

NAV_CACHE_KEY = "nav:v1"


def build_nav() -> dict:
    from catalog.models import Category, Theme

    def cat(c):
        return {"name": c.name, "slug": c.slug, "icon": c.icon, "kind": c.kind}

    roots = list(Category.objects.filter(parent__isnull=True, is_active=True).order_by("sort_order", "name"))
    children = {}
    for c in Category.objects.filter(parent__isnull=False, is_active=True).order_by("sort_order", "name"):
        children.setdefault(c.parent_id, []).append(cat(c))
    sets_series = [
        {"name": t.display_name, "short": t.short_name, "slug": t.slug, "accent": t.accent}
        for t in Theme.objects.filter(is_primary=True).order_by("sort_order", "name")
    ]
    fig_series = [
        {"name": t.display_name, "short": t.short_name, "slug": t.slug, "accent": t.accent}
        for t in Theme.objects.filter(show_in_minifigs=True).order_by("sort_order", "name")
    ]
    return {
        "roots": [dict(cat(c), children=children.get(c.pk, [])) for c in roots],
        "by_kind": {c.kind: dict(cat(c), children=children.get(c.pk, [])) for c in roots},
        "sets_series": sets_series,
        "fig_series": fig_series,
    }


def get_nav() -> dict:
    nav = cache.get(NAV_CACHE_KEY)
    if nav is None:
        nav = build_nav()
        cache.set(NAV_CACHE_KEY, nav, 600)
    return nav


def shop(request):
    return {"SHOP": settings.SHOP, "nav": get_nav()}
