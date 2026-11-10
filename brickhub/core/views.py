import posixpath

from django.conf import settings
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_safe
from django.views.static import serve
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_page

from django.core.cache import cache

from catalog.models import Category, Color, LegoSet, Part, Product, Theme
from catalog.views import recently_viewed

from .seo import organization_jsonld


HOME_FINDER_CATEGORIES = ["tsehlynky", "skosy", "plastyny", "plytky", "kolesa-ta-shyny", "vikna-ta-dveri",
                          "shesterni", "elementy-technic"]

def home(request):
    active = Product.objects.active().with_related()
    # only products that have the owner's own photo appear in the hero collage
    hero = list(active.in_stock().filter(images__isnull=False).exclude(kind="part").distinct().order_by(
        "-is_featured", "-created_at")[:6])
    popular = list(active.filter(is_featured=True).exclude(kind="part").order_by("-views_count", "-sold_count",
                                                                                "-created_at")[:10])
    new = list(active.filter(is_new=True).order_by("-created_at")[:10])
    bestsellers = list(active.filter(Q(is_bestseller=True) | Q(sold_count__gt=0)).order_by(
        "-sold_count", "-is_featured", "-created_at")[:10])
    latest = list(active.in_stock().order_by("-created_at")[:10])
    minifigs = list(active.filter(kind="minifig", condition="new").order_by("-is_featured", "-views_count",
                                                                          "-created_at")[:10])
    series = list(Theme.objects.filter(is_primary=True).annotate(
        n=Count("products", filter=Q(products__is_active=True))).order_by("sort_order"))
    part_categories = list(Category.objects.filter(kind="part", parent__isnull=False, is_active=True).annotate(
        n=Count("products", filter=Q(products__is_active=True))).order_by("sort_order"))
    by_slug = {c.slug: c for c in part_categories}
    # the part-finder promo shows drawings of classic parts; the tiles show the 12 fullest categories
    finder_categories = [by_slug[s] for s in HOME_FINDER_CATEGORIES if s in by_slug]
    part_categories = sorted(part_categories, key=lambda c: -c.n)[:12]
    stats = cache.get("home:stats")
    if stats is None:
        stats = {"sets": LegoSet.objects.count(), "parts": Part.objects.count(),
                 "colors": Color.objects.filter(is_active=True).count()}
        cache.set("home:stats", stats, 3600)
    seo = {
        "title": f"{settings.SHOP['NAME']} — інтернет-магазин LEGO в Україні: набори, деталі, мініфігурки",
        "description": "Оригінальні набори LEGO, окремі деталі за номером Design ID і кольором та мініфігурки. "
                       "Доставка Новою поштою та Укрпоштою по всій Україні.",
        "canonical": request.build_absolute_uri("/"),
        "jsonld": [organization_jsonld(request), {
            "@context": "https://schema.org", "@type": "WebSite", "url": request.build_absolute_uri("/"),
            "potentialAction": {"@type": "SearchAction",
                                "target": request.build_absolute_uri(reverse("catalog:search")) + "?q={query}",
                                "query-input": "required name=query"}}],
    }
    return render(request, "core/home.html", {
        "hero": hero, "popular": popular, "new": new, "bestsellers": bestsellers, "latest": latest,
        "minifigs": minifigs, "series": series, "part_categories": part_categories,
        "finder_categories": finder_categories,
        "recent": recently_viewed(request), "seo": seo, "stats": stats,
    })


PAGES = {
    "delivery": ("Доставка та оплата", "core/pages/delivery.html"),
    "about": ("Про магазин", "core/pages/about.html"),
    "contacts": ("Контакти", "core/pages/contacts.html"),
    "returns": ("Обмін та повернення", "core/pages/returns.html"),
    "terms": ("Умови використання", "core/pages/terms.html"),
    "privacy": ("Політика конфіденційності", "core/pages/privacy.html"),
    "guide": ("Як знайти деталь за номером", "core/pages/guide.html"),
}


def page(request, key):
    title, template = PAGES[key]
    return render(request, template, {"page_title": title, "crumbs": [(title, None)],
                                      "seo": {"title": title, "description": f"{title} — {settings.SHOP['NAME']}"}})


@cache_page(60 * 60)
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /kabinet/",
        "Disallow: /koshyk/",
        "Disallow: /zamovlennia/",
        "Disallow: /panel/",
        "Disallow: /django-admin/",
        "Disallow: /poshuk/",
        "Disallow: /api/",
        "Disallow: /obrane/",
        "Disallow: /porivniannia/",
        f"Sitemap: {request.build_absolute_uri(reverse('core:sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def error_404(request, exception=None):
    return render(request, "404.html", {"seo": {"title": "Сторінку не знайдено", "noindex": True}}, status=404)


def error_500(request):
    from django.template import loader

    return HttpResponse(loader.get_template("500.html").render(), status=500)


@require_safe
def media_file(request, path):
    """An uploaded product photo, for servers that do not serve /media/ themselves (settings.SERVE_MEDIA)."""
    if posixpath.normpath(path) != path or not path.startswith("products/"):
        raise Http404  # no "..", "//" or anything outside the product photos folder
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    # every upload gets a new file name, so browsers may keep photos for a long time
    response["Cache-Control"] = "public, max-age=2592000"
    return response
