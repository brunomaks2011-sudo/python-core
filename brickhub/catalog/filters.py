"""Listing filters, facets and sorting for catalogue pages."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, F, Max, Min, Q

from .models import Category, Color, Product, Theme
from .search import search_products

SORT_OPTIONS = [
    ("popular", "За популярністю"),
    ("new", "Новинки"),
    ("price_asc", "Від дешевих"),
    ("price_desc", "Від дорогих"),
    ("name", "За назвою"),
    ("rating", "За рейтингом"),
]
SORT_FIELDS = {
    "popular": ("-is_featured", "-sold_count", "-views_count", "-created_at"),
    "new": ("-created_at",),
    "price_asc": ("price", "-created_at"),
    "price_desc": ("-price", "-created_at"),
    "name": ("title",),
    "rating": ("-rating_avg", "-reviews_count", "-sold_count"),
}
PER_PAGE_OPTIONS = (24, 48, 96)

COLLECTIONS = {
    "novynky": ("Новинки", "Свіжі набори та деталі, що щойно з'явилися в магазині.", Q(is_new=True)),
    "rozprodazh": ("Розпродаж", "Товари зі знижкою — поки є в наявності.", Q(old_price__gt=F("price"))),
    "vzhyvani-nabory": ("Набори б/у", "Перевірені набори з повною комплектацією за приємною ціною.",
                        Q(kind="set", condition="used")),
    "ridkisni": ("Рідкісні та колекційні", "Зняті з виробництва флагмани та колекційні позиції.", Q(is_rare=True)),
    "prozori-detali": ("Прозорі деталі", "Деталі прозорих кольорів: скло, вогні, кристали та леза.",
                       Q(kind="part", color__is_transparent=True)),
    "khity-prodazhu": ("Хіти продажів", "Те, що купують найчастіше.", Q(is_bestseller=True) | Q(sold_count__gt=0)),
    "populiarni": ("Популярні товари", "Вибір наших покупців і команди BRICK HUB.", Q(is_featured=True)),
    "inshi-serii": ("Інші серії LEGO", "Jurassic World, Disney, DC, Botanicals, DREAMZzz та інші серії.",
                    Q(kind="set") & ~Q(theme__is_primary=True)),
    "inshi-personazhi": ("Інші персонажі", "Мініфігурки з інших серій LEGO.",
                         Q(kind="minifig") & ~Q(theme__show_in_minifigs=True)),
    "ostanni-nadkhodzhennia": ("Останні надходження", "Що щойно приїхало на склад.", Q(inventory__quantity__gt=0)),
}


def _dec(v):
    try:
        return Decimal(str(v).replace(",", ".").replace(" ", "")) if v not in (None, "") else None
    except InvalidOperation:
        return None


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@dataclass
class Listing:
    page: object
    paginator: object
    total: int
    sort: str
    per_page: int
    query: str
    parsed: object = None
    facets: dict = field(default_factory=dict)
    active: list = field(default_factory=list)
    params: dict = field(default_factory=dict)
    view: str = "grid"

    def url_with(self, **changes) -> str:
        params = {k: v for k, v in self.params.items() if v not in (None, "", [])}
        for k, v in changes.items():
            if v in (None, "", []):
                params.pop(k, None)
            else:
                params[k] = v
        return "?" + urlencode(params, doseq=True) if params else "?"

    def page_url(self, number: int) -> str:
        params = {k: v for k, v in self.params.items() if v not in (None, "", [])}
        params["page"] = number
        if number == 1:
            params.pop("page")
        return "?" + urlencode(params, doseq=True) if params else "?"


def build_listing(request, base_qs, *, default_sort="popular", facets=("kind", "theme", "category", "color",
                                                                       "condition", "price", "year", "pieces")):
    g = request.GET
    params = {
        "q": g.get("q", "").strip()[:120],
        "kind": [k for k in g.getlist("kind") if k in dict(Product.KINDS)],
        "theme": g.getlist("theme")[:20],
        "category": g.getlist("category")[:20],
        "color": g.getlist("color")[:30],
        "condition": g.get("condition", "") if g.get("condition") in ("new", "used") else "",
        "stock": "1" if g.get("stock") == "1" else "",
        "price_min": g.get("price_min", ""),
        "price_max": g.get("price_max", ""),
        "year_min": g.get("year_min", ""),
        "year_max": g.get("year_max", ""),
        "pieces_min": g.get("pieces_min", ""),
        "pieces_max": g.get("pieces_max", ""),
        "sort": g.get("sort", "") if g.get("sort") in SORT_FIELDS else "",
        "per_page": g.get("per_page", "") if _int(g.get("per_page")) in PER_PAGE_OPTIONS else "",
        "view": g.get("view", "") if g.get("view") in ("grid", "list") else "",
    }
    qs = base_qs.active()
    facet_base = qs
    parsed = None
    if params["q"]:
        qs, parsed = search_products(qs, params["q"])
        facet_base = qs
    active = []

    def chip(label, **remove):
        active.append({"label": label, "url": None, "remove": remove})

    if params["kind"]:
        qs = qs.filter(kind__in=params["kind"])
        for k in params["kind"]:
            chip(dict(Product.KINDS)[k], kind=[x for x in params["kind"] if x != k])
    if params["theme"]:
        themes = list(Theme.objects.filter(slug__in=params["theme"]))
        ids = []
        for t in themes:
            ids += t.descendant_ids()
            chip(t.display_name, theme=[x for x in params["theme"] if x != t.slug])
        qs = qs.filter(theme_id__in=ids)
    if params["category"]:
        cats = list(Category.objects.filter(slug__in=params["category"]))
        ids = []
        for c in cats:
            ids += c.descendant_ids()
            chip(c.name, category=[x for x in params["category"] if x != c.slug])
        qs = qs.filter(category_id__in=ids)
    if params["color"]:
        colors = list(Color.objects.filter(slug__in=params["color"]))
        qs = qs.filter(color__in=colors)
        for c in colors:
            chip(c.display_name, color=[x for x in params["color"] if x != c.slug])
    if params["condition"]:
        qs = qs.filter(condition=params["condition"])
        chip("Новий" if params["condition"] == "new" else "Б/у", condition="")
    if params["stock"]:
        qs = qs.filter(inventory__quantity__gt=0)
        chip("В наявності", stock="")
    pmin, pmax = _dec(params["price_min"]), _dec(params["price_max"])
    if pmin is not None:
        qs = qs.filter(price__gte=pmin)
    if pmax is not None:
        qs = qs.filter(price__lte=pmax)
    if pmin is not None or pmax is not None:
        chip(f"Ціна: {params['price_min'] or '0'}–{params['price_max'] or '∞'} ₴", price_min="", price_max="")
    ymin, ymax = _int(params["year_min"]), _int(params["year_max"])
    if ymin:
        qs = qs.filter(Q(lego_set__year__gte=ymin) | Q(minifigure__year__gte=ymin))
    if ymax:
        qs = qs.filter(Q(lego_set__year__lte=ymax) | Q(minifigure__year__lte=ymax))
    if ymin or ymax:
        chip(f"Рік: {ymin or '…'}–{ymax or '…'}", year_min="", year_max="")
    nmin, nmax = _int(params["pieces_min"]), _int(params["pieces_max"])
    if nmin:
        qs = qs.filter(lego_set__pieces__gte=nmin)
    if nmax:
        qs = qs.filter(lego_set__pieces__lte=nmax)
    if nmin or nmax:
        chip(f"Деталей: {nmin or 0}–{nmax or '∞'}", pieces_min="", pieces_max="")

    sort = params["sort"] or ("relevance" if params["q"] else default_sort)
    if sort == "relevance":
        qs = qs.order_by("-rank", "-inventory__quantity", "-sold_count", "title")
    else:
        order = SORT_FIELDS[sort]
        if parsed and parsed.numbers:
            order = ("-rank",) + order
        qs = qs.order_by(*order)
    qs = qs.with_related()

    per_page = _int(params["per_page"]) or 24
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(g.get("page"))
    listing = Listing(page=page, paginator=paginator, total=paginator.count, sort=sort, per_page=per_page,
                      query=params["q"], parsed=parsed, active=active, params=params,
                      view=params["view"] or "grid")
    listing.facets = compute_facets(facet_base, facets)
    for chip_ in active:
        chip_["url"] = listing.url_with(**chip_["remove"])
    return listing


def compute_facets(qs, wanted) -> dict:
    out = {}
    if "kind" in wanted:
        labels = dict(Product.KINDS)
        rows = qs.order_by().values("kind").annotate(n=Count("id"))
        kinds = [{"value": r["kind"], "label": labels.get(r["kind"], r["kind"]), "count": r["n"]} for r in rows]
        if len(kinds) > 1:
            out["kind"] = sorted(kinds, key=lambda k: list(labels).index(k["value"]))
    if "theme" in wanted:
        rows = qs.order_by().exclude(theme__isnull=True).values("theme__slug", "theme__title", "theme__name",
                                                               "theme__accent").annotate(n=Count("id"))
        themes = [{"value": r["theme__slug"], "label": r["theme__title"] or r["theme__name"], "count": r["n"],
                   "accent": r["theme__accent"]} for r in rows]
        if len(themes) > 1:
            out["theme"] = sorted(themes, key=lambda t: (-t["count"], t["label"]))
    if "category" in wanted:
        rows = qs.order_by().filter(kind="part").exclude(category__isnull=True).values(
            "category__slug", "category__name").annotate(n=Count("id"))
        cats = [{"value": r["category__slug"], "label": r["category__name"], "count": r["n"]} for r in rows]
        if len(cats) > 1:
            out["category"] = sorted(cats, key=lambda c: c["label"])
    if "color" in wanted:
        rows = qs.order_by().exclude(color__isnull=True).values(
            "color__slug", "color__name", "color__name_uk", "color__rgb", "color__is_transparent",
            "color__sort_order").annotate(n=Count("id"))
        colors = [{"value": r["color__slug"], "label": r["color__name_uk"] or r["color__name"],
                   "official": r["color__name"], "hex": "#" + (r["color__rgb"] or "CCCCCC"),
                   "trans": r["color__is_transparent"], "count": r["n"], "order": r["color__sort_order"]}
                  for r in rows]
        if colors:
            out["color"] = sorted(colors, key=lambda c: (c["order"], c["label"]))
    if "condition" in wanted:
        rows = dict(qs.order_by().values_list("condition").annotate(n=Count("id")))
        if len(rows) > 1:
            out["condition"] = [{"value": "new", "label": "Новий", "count": rows.get("new", 0)},
                                {"value": "used", "label": "Б/у", "count": rows.get("used", 0)}]
    agg = qs.order_by().aggregate(pmin=Min("price"), pmax=Max("price"), ymin=Min("lego_set__year"),
                                  ymax=Max("lego_set__year"), nmin=Min("lego_set__pieces"),
                                  nmax=Max("lego_set__pieces"), in_stock=Count("id", filter=Q(inventory__quantity__gt=0)))
    if "price" in wanted and agg["pmin"] is not None:
        out["price"] = {"min": int(agg["pmin"]), "max": int(agg["pmax"]) + 1}
    if "year" in wanted and agg["ymin"]:
        out["year"] = {"min": agg["ymin"], "max": agg["ymax"]}
    if "pieces" in wanted and agg["nmin"]:
        out["pieces"] = {"min": agg["nmin"], "max": agg["nmax"]}
    out["in_stock"] = agg["in_stock"]
    return out
