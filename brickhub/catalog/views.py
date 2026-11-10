from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Exists, F, Min, OuterRef, Prefetch, Q, Sum, TextField
from django.db.models.functions import Cast
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_GET, require_POST

from cart import services as cart_services
from core.seo import breadcrumbs_jsonld, product_jsonld

from .filters import COLLECTIONS, SORT_OPTIONS, PER_PAGE_OPTIONS, build_listing
from .forms import ReviewForm
from .media import has_photo, image_urls
from .models import (
    Category, Color, Element, Part, Product, ProductImage, Review, StockNotification, Theme, category_tree,
)
from .part_art import render_minifig_svg, render_part_svg
from .search import catalog_matches, search_products
from .variants import color_variants, condition_variants

RECENT_KEY = "recent"


def _listing_context(listing, **extra):
    ctx = {"listing": listing, "products": listing.page.object_list, "sort_options": SORT_OPTIONS,
           "per_page_options": PER_PAGE_OPTIONS}
    ctx.update(extra)
    return ctx


def _seo_list(title, description, request, page=None, noindex=False):
    canonical = request.build_absolute_uri(request.path)
    if page and page.number > 1:
        canonical += f"?page={page.number}"
    return {"title": title, "description": description[:300], "canonical": canonical,
            "noindex": noindex or bool(set(request.GET) - {"page"})}


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------
def catalog_index(request):
    listing = build_listing(request, Product.objects.all())
    crumbs = [("Каталог", None)]
    return render(request, "catalog/listing.html", _listing_context(
        listing, heading="Каталог LEGO", lead="Набори, окремі деталі та мініфігурки — усе в одному місці.",
        crumbs=crumbs, seo=_seo_list("Каталог LEGO — набори, деталі, мініфігурки", "Каталог оригінальних наборів, "
                                     "деталей і мініфігурок LEGO з доставкою по Україні.", request, listing.page)))


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    if category.slug == "prozori-detali":
        return collection_detail(request, "prozori-detali", category=category)
    ids = category.descendant_ids()
    kind_map = {k: k for k in ("set", "part", "minifig", "keychain", "book", "accessory")}
    if category.parent_id is None and category.kind in kind_map:
        base = Product.objects.filter(kind=kind_map[category.kind])
    else:
        base = Product.objects.filter(category_id__in=ids)
    listing = build_listing(request, base, default_sort="popular" if category.kind != "part" else "popular")
    ancestors = category.ancestors()
    crumbs = [("Каталог", reverse("catalog:index"))]
    crumbs += [(a.name, a.get_absolute_url()) for a in ancestors]
    crumbs.append((category.name, None))
    children = list(category.children.filter(is_active=True))
    if not children and len(ancestors) >= 2:
        # third level: the neighbouring subcategories, this one highlighted
        children = list(category.parent.children.filter(is_active=True))
    nav_series = None
    if category.kind == "set" and category.parent_id is None:
        nav_series = Theme.objects.filter(is_primary=True)
    if category.kind == "minifig" and category.parent_id is None:
        nav_series = Theme.objects.filter(show_in_minifigs=True)
    title = category.seo_title or f"{category.name} — купити в Україні"
    return render(request, "catalog/listing.html", _listing_context(
        listing, heading=category.name, lead=category.description, category=category, children=children,
        nav_series=nav_series, crumbs=crumbs,
        seo=_seo_list(title, category.seo_description or category.description or category.name, request,
                      listing.page)))


def theme_detail(request, slug):
    theme = get_object_or_404(Theme, slug=slug)
    ids = theme.descendant_ids()
    kind = request.GET.get("kind")
    base = Product.objects.filter(theme_id__in=ids)
    counts = dict(base.active().order_by().values_list("kind").annotate(n=Count("id")))
    listing = build_listing(request, base, facets=("kind", "category", "condition", "price", "year", "pieces"))
    crumbs = [("Каталог", reverse("catalog:index")), ("Набори LEGO", reverse("catalog:category", args=["nabory"])),
              (theme.display_name, None)]
    return render(request, "catalog/listing.html", _listing_context(
        listing, heading=theme.display_name, lead=theme.description, theme=theme, crumbs=crumbs, kind_counts=counts,
        active_kind=kind,
        seo=_seo_list(f"{theme.display_name} — набори та мініфігурки", theme.description or theme.display_name,
                      request, listing.page)))


def collection_detail(request, slug, category=None):
    if slug not in COLLECTIONS:
        raise Http404
    title, lead, cond = COLLECTIONS[slug]
    base = Product.objects.filter(cond)
    default_sort = {"novynky": "new", "khity-prodazhu": "popular", "rozprodazh": "price_asc"}.get(slug, "popular")
    listing = build_listing(request, base, default_sort=default_sort)
    crumbs = [("Каталог", reverse("catalog:index")), (title, None)]
    return render(request, "catalog/listing.html", _listing_context(
        listing, heading=title, lead=lead, collection=slug, crumbs=crumbs, category=category,
        seo=_seo_list(f"{title} LEGO — BRICK HUB", lead, request, listing.page)))


def search(request):
    q = request.GET.get("q", "").strip()
    listing = build_listing(request, Product.objects.all())
    parsed = listing.parsed
    design = None
    catalog = []
    if parsed and parsed.numbers:
        for num in parsed.numbers:
            part = Part.objects.filter(Q(design_id__iexact=num) | Q(elements__element_id=num)).distinct().first()
            if part and part.products.filter(is_active=True).exists():
                agg = part.products.filter(is_active=True).aggregate(colors=Count("color", distinct=True),
                                                                     pmin=Min("price"),
                                                                     stock=Sum("inventory__quantity"))
                design = {"part": part, **agg}
                break
        if not listing.total:
            catalog = catalog_matches(parsed)
    crumbs = [("Пошук", None)]
    return render(request, "catalog/search.html", _listing_context(
        listing, heading=f"Результати пошуку «{q}»" if q else "Пошук", crumbs=crumbs, design=design,
        catalog=catalog, seo={"title": f"Пошук: {q}" if q else "Пошук", "description": "Пошук по каталогу LEGO",
                              "noindex": True}))


@require_GET
def suggest(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"query": q, "items": [], "total": 0})
    qs, parsed = search_products(Product.objects.active().with_related(), q)
    qs = qs.order_by("-rank", "-inventory__quantity", "-sold_count", "title")
    total = qs.count()
    items = []
    for p in qs[:8]:
        src, fallback = image_urls(p)
        items.append({
            "title": p.title, "url": p.get_absolute_url(), "img": src, "fallback": fallback,
            "number": p.official_number, "kind": p.get_kind_display(), "price": f"{p.price:.2f}",
            "color": p.color.display_name if p.color_id else "", "hex": p.color.hex if p.color_id else "",
            "stock": p.stock, "condition": p.get_condition_display(),
        })
    design = None
    for num in parsed.numbers:
        part = Part.objects.filter(design_id__iexact=num).first()
        if part:
            n = part.products.filter(is_active=True).values("color").distinct().count()
            if n:
                design = {"id": part.design_id, "name": part.display_name, "colors": n,
                          "url": reverse("catalog:part_design", args=[part.design_id])}
            break
    return JsonResponse({"query": q, "items": items, "total": total, "design": design,
                         "all_url": reverse("catalog:search") + "?q=" + q})


# ---------------------------------------------------------------------------
# Product page
# ---------------------------------------------------------------------------
def _remember(request, product):
    recent = [pid for pid in request.session.get(RECENT_KEY, []) if pid != product.pk]
    recent.insert(0, product.pk)
    request.session[RECENT_KEY] = recent[:16]
    seen = request.session.get("seen", [])
    if product.pk not in seen:
        Product.objects.filter(pk=product.pk).update(views_count=F("views_count") + 1)
        request.session["seen"] = (seen + [product.pk])[-200:]


def recently_viewed(request, exclude=None, limit=8):
    ids = [pid for pid in request.session.get(RECENT_KEY, []) if pid != exclude][:limit]
    if not ids:
        return []
    found = {p.pk: p for p in Product.objects.active().filter(pk__in=ids).with_related()}
    return [found[i] for i in ids if i in found]


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.with_related().prefetch_related(
        Prefetch("reviews", queryset=Review.objects.filter(is_published=True).select_related("user"))), slug=slug)
    if not product.is_active and not request.user.is_staff:
        raise Http404
    _remember(request, product)
    colors = color_variants(product)
    conditions = condition_variants(product)
    similar = Product.objects.active().in_stock().exclude(pk=product.pk).with_related()
    if product.kind == "part" and product.part_id:
        similar = similar.filter(kind="part", category_id=product.category_id).exclude(part_id=product.part_id)
        similar = similar.order_by("-sold_count", "-is_featured")
        same_color = list(similar.filter(color_id=product.color_id)[:8]) if product.color_id else []
        similar = same_color or list(similar[:8])
    elif product.theme_id:
        similar = list(similar.filter(theme_id=product.theme_id, kind=product.kind).order_by("-is_featured",
                                                                                            "-sold_count")[:8])
    else:
        similar = list(similar.filter(kind=product.kind).order_by("-sold_count")[:8])
    contains_figs = []
    if product.kind == "set" and product.lego_set_id:
        contains_figs = list(
            Product.objects.active().filter(kind="minifig", condition="new")
            .annotate(appears=Cast("minifigure__appears_in", TextField()))
            .filter(appears__contains=f'"{product.lego_set.number}"').with_related()[:8])
    reviews = list(product.reviews.all())
    my_review = None
    if request.user.is_authenticated:
        my_review = next((r for r in reviews if r.user_id == request.user.id), None)
    element_id = product.element_id
    crumbs = [("Каталог", reverse("catalog:index"))]
    if product.category_id:
        crumbs += [(a.name, a.get_absolute_url()) for a in product.category.ancestors()]
        crumbs.append((product.category.name, product.category.get_absolute_url()))
    if product.theme_id and product.kind in ("set", "minifig"):
        crumbs.append((product.theme.display_name, product.theme.get_absolute_url()))
    crumbs.append((product.title, None))
    photo = None
    if has_photo(product):
        src = product.main_image.share_url
        photo = request.build_absolute_uri(src) if src.startswith("/") else src
    seo = {
        "title": seo_title(product),
        "description": (product.description or product.title)[:300],
        "canonical": request.build_absolute_uri(product.get_absolute_url()),
        "image": photo,
        "type": "product",
        "jsonld": [product_jsonld(request, product, photo), breadcrumbs_jsonld(request, crumbs)],
    }
    return render(request, "catalog/product.html", {
        "product": product, "color_variants": colors, "condition_variants": conditions,
        "similar": similar, "recent": recently_viewed(request, product.pk),
        "reviews": reviews, "my_review": my_review, "review_form": ReviewForm(instance=my_review),
        "element_id": element_id, "crumbs": crumbs, "seo": seo, "contains_figs": contains_figs,
        "is_favorite": product.pk in cart_services.favorite_ids(request),
        "in_compare": product.pk in cart_services.compare_ids(request),
    })


def seo_title(product) -> str:
    if product.kind == "set":
        theme = product.theme.display_name if product.theme_id else "LEGO"
        return f"{theme} {product.official_number} {product.title} — купити"
    if product.kind == "part":
        color = product.color.display_name if product.color_id else ""
        return f"Деталь LEGO {product.official_number} {product.title} {color}".strip()
    if product.kind == "minifig":
        return f"Мініфігурка LEGO {product.official_number} {product.title}"
    return product.title


# ---------------------------------------------------------------------------
# Parts (BrickLink-style)
# ---------------------------------------------------------------------------
def part_finder(request):
    q = request.GET.get("q", "").strip()
    color_slug = request.GET.get("color", "")
    cat_slug = request.GET.get("category", "")
    parts = Part.objects.filter(products__is_active=True, products__kind="part")
    color = Color.objects.filter(slug=color_slug).first() if color_slug else None
    category = Category.objects.filter(slug=cat_slug, kind="part").first() if cat_slug else None
    if q:
        for tok in q.lower().split():
            parts = parts.filter(Q(design_id__iexact=tok) | Q(name__icontains=tok) | Q(name_uk__icontains=tok) |
                                 Q(alternate_ids__icontains=tok) | Q(elements__element_id=tok) |
                                 Q(design_id__istartswith=tok))
    if color:
        parts = parts.filter(products__color=color)
    if category:
        parts = parts.filter(category_id__in=category.descendant_ids())
    parts = parts.annotate(
        n_colors=Count("products__color", distinct=True, filter=Q(products__is_active=True)),
        pmin=Min("products__price", filter=Q(products__is_active=True)),
        stock=Sum("products__inventory__quantity", filter=Q(products__is_active=True)),
    ).select_related("category").distinct().order_by("category__sort_order", "design_id")
    from django.core.paginator import Paginator

    page = Paginator(parts, 36).get_page(request.GET.get("page"))
    page_parts = list(page.object_list)
    swatches = {}
    for row in (Product.objects.active().filter(kind="part", part__in=page_parts)
                .values("part_id", "color__rgb", "color__name", "color__name_uk", "color__is_transparent",
                        "color__sort_order").distinct().order_by("color__sort_order")):
        swatches.setdefault(row["part_id"], []).append(row)
    rows = []
    for part in page_parts:
        sample = _sample_lot(part, color)
        colors_of_part = swatches.get(part.pk, [])
        rows.append({"part": part, "sample": sample, "swatches": colors_of_part[:8],
                     "more_colors": max(0, len(colors_of_part) - 8)})
    colors = Color.objects.filter(products__kind="part", products__is_active=True).annotate(
        n=Count("products", distinct=True)).order_by("sort_order", "name")
    categories = [{"slug": c.slug, "pk": c.pk, "name": c.name if depth == 1 else f"— {c.name}"}
                  for c, depth, _path in category_tree(Category.objects.filter(kind="part", is_active=True))
                  if depth >= 1]
    crumbs = [("Каталог", reverse("catalog:index")), ("Пошук деталей", None)]
    return render(request, "catalog/part_finder.html", {
        "rows": rows, "page": page, "q": q, "color": color, "category": category, "colors": colors,
        "categories": categories, "crumbs": crumbs,
        "seo": {"title": "Пошук деталей LEGO за номером і кольором",
                "description": "Знайдіть деталь LEGO за Design ID, Element ID або назвою, оберіть колір і "
                               "купіть потрібну кількість.", "noindex": bool(q or color_slug or cat_slug)},
    })


def _sample_lot(part, color=None):
    """A listing of the part to represent it: one with the owner's photo first, then the best stocked."""
    qs = (Product.objects.active().filter(part=part)
          .annotate(has_photo=Exists(ProductImage.objects.filter(product=OuterRef("pk"))))
          .select_related("color", "part", "inventory").prefetch_related("images"))
    if color:
        picked = qs.filter(color=color).order_by("-has_photo", "-inventory__quantity").first()
        if picked:
            return picked
    return qs.order_by("-has_photo", "-inventory__quantity").first()


def part_design(request, design_id):
    part = get_object_or_404(Part.objects.select_related("category", "part_category"), design_id=design_id)
    lots = list(Product.objects.active().filter(part=part).select_related("color", "inventory")
                .prefetch_related("images").order_by("color__sort_order", "color__name", "condition"))
    if not lots:
        raise Http404
    elements = {(e.color_id): e.element_id for e in Element.objects.filter(part=part)}
    for lot in lots:
        lot.el_id = elements.get(lot.color_id, "")
    main = max(lots, key=lambda p: (p.main_image is not None, p.stock > 0, p.stock))
    crumbs = [("Каталог", reverse("catalog:index")), ("Деталі LEGO", reverse("catalog:category", args=["detali"]))]
    if part.category_id:
        crumbs += [(a.name, a.get_absolute_url()) for a in part.category.ancestors() if a.slug != "detali"]
        crumbs.append((part.category.name, part.category.get_absolute_url()))
    crumbs.append((f"{part.design_id} {part.display_name}", None))
    related = Part.objects.filter(category_id=part.category_id, products__is_active=True).exclude(
        pk=part.pk).distinct()[:12] if part.category_id else []
    related_rows = []
    for rp in related:
        sample = _sample_lot(rp)
        if sample:
            related_rows.append({"part": rp, "sample": sample})
    return render(request, "catalog/part_design.html", {
        "part": part, "lots": lots, "main": main, "crumbs": crumbs, "related": related_rows,
        "colors_count": len({lot.color_id for lot in lots}),
        "seo": {"title": f"Деталь LEGO {part.design_id} {part.display_name} — усі кольори",
                "description": f"{part.name} (Design ID {part.design_id}) у {len(lots)} варіантах кольору та стану. "
                               "Ціна за штуку, наявність на складі.",
                "canonical": request.build_absolute_uri(request.path)},
    })


def colors_index(request):
    colors = Color.objects.filter(is_active=True).annotate(
        n=Count("products", filter=Q(products__is_active=True, products__kind="part"), distinct=True)
    ).order_by("sort_order", "name")
    show_all = request.GET.get("all") == "1"
    if not show_all:
        colors = colors.filter(n__gt=0)
    crumbs = [("Каталог", reverse("catalog:index")), ("Кольори LEGO", None)]
    return render(request, "catalog/colors.html", {
        "colors": colors, "show_all": show_all, "crumbs": crumbs,
        "seo": {"title": "Кольори LEGO — таблиця з номерами BrickLink",
                "description": "Довідник кольорів LEGO: офіційні назви, українські назви, номери BrickLink "
                               "і Rebrickable та HEX."},
    })


def color_detail(request, slug):
    color = get_object_or_404(Color, slug=slug)
    listing = build_listing(request, Product.objects.filter(kind="part", color=color),
                            facets=("category", "condition", "price"))
    crumbs = [("Каталог", reverse("catalog:index")), ("Кольори LEGO", reverse("catalog:colors")),
              (color.display_name, None)]
    return render(request, "catalog/listing.html", _listing_context(
        listing, heading=f"Деталі кольору «{color.display_name}»", color=color, crumbs=crumbs,
        lead=f"Офіційна назва: {color.name}. Номер кольору: {color.code}.",
        seo=_seo_list(f"Деталі LEGO кольору {color.display_name} ({color.name})",
                      f"Окремі деталі LEGO у кольорі {color.name}.", request, listing.page)))


# ---------------------------------------------------------------------------
# Favourites, comparison, reviews, notifications
# ---------------------------------------------------------------------------
def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get(
        "accept", "")


@require_POST
def toggle_favorite(request, pk):
    product = get_object_or_404(Product, pk=pk)
    added = cart_services.toggle_favorite(request, product)
    if _wants_json(request):
        return JsonResponse({"ok": True, "active": added, "count": len(cart_services.favorite_ids(request))})
    messages.success(request, "Додано в обране" if added else "Прибрано з обраного")
    return redirect(request.POST.get("next") or product.get_absolute_url())


def favorites(request):
    ids = list(cart_services.favorite_ids(request))
    products = Product.objects.filter(pk__in=ids).with_related().order_by("-created_at")
    crumbs = [("Обране", None)]
    return render(request, "catalog/favorites.html", {"products": products, "crumbs": crumbs,
                                                      "seo": {"title": "Обране", "noindex": True}})


@require_POST
def toggle_compare(request, pk):
    product = get_object_or_404(Product, pk=pk)
    added, note = cart_services.toggle_compare(request, product)
    if _wants_json(request):
        return JsonResponse({"ok": True, "active": added, "count": len(cart_services.compare_ids(request)),
                             "message": note})
    if note:
        messages.info(request, note)
    messages.success(request, "Додано до порівняння" if added else "Прибрано з порівняння")
    return redirect(request.POST.get("next") or product.get_absolute_url())


def compare(request):
    ids = cart_services.compare_ids(request)
    found = {p.pk: p for p in Product.objects.filter(pk__in=ids).with_related()}
    products = [found[i] for i in ids if i in found]
    rows = compare_rows(products)
    crumbs = [("Порівняння", None)]
    return render(request, "catalog/compare.html", {"products": products, "rows": rows, "crumbs": crumbs,
                                                    "seo": {"title": "Порівняння товарів", "noindex": True}})


def compare_rows(products):
    def val(p, key):
        s = p.lego_set
        return {
            "kind": p.get_kind_display(),
            "number": p.official_number,
            "theme": p.theme.display_name if p.theme_id else "—",
            "condition": p.get_condition_display(),
            "year": p.year or "—",
            "pieces": (s.pieces if s and s.pieces else "—"),
            "minifigs": (s.minifigs_count if s and s.minifigs_count is not None else "—"),
            "age": (f"{s.age_min}+" if s and s.age_min else "—"),
            "color": p.color.display_name if p.color_id else "—",
            "stock": "Є" if p.in_stock else "Немає",
            "rating": f"{p.rating_avg:.1f} ({p.reviews_count})" if p.reviews_count else "—",
        }[key]

    labels = [("kind", "Тип"), ("number", "Номер LEGO"), ("theme", "Серія"), ("condition", "Стан"), ("year", "Рік"),
              ("pieces", "Деталей"), ("minifigs", "Мініфігурок"), ("age", "Вік"), ("color", "Колір"),
              ("stock", "Наявність"), ("rating", "Рейтинг")]
    rows = []
    for key, label in labels:
        values = [val(p, key) for p in products]
        if all(v in ("—", "", None) for v in values):
            continue
        rows.append({"label": label, "values": values, "differs": len({str(v) for v in values}) > 1})
    return rows


@login_required
@require_POST
def review_create(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    existing = Review.objects.filter(product=product, user=request.user).first()
    form = ReviewForm(request.POST, instance=existing)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.save()
        product.refresh_rating()
        messages.success(request, "Дякуємо за відгук!")
    else:
        messages.error(request, "Перевірте оцінку та текст відгуку.")
    return redirect(product.get_absolute_url() + "#reviews")


@require_POST
def stock_notify(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    email = (request.POST.get("email") or (request.user.email if request.user.is_authenticated else "")).strip()
    try:
        validate_email(email)
    except ValidationError:
        msg = "Вкажіть коректну електронну пошту."
        if _wants_json(request):
            return JsonResponse({"ok": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect(product.get_absolute_url())
    StockNotification.objects.get_or_create(
        product=product, email=email.lower(), notified_at__isnull=True,
        defaults={"user": request.user if request.user.is_authenticated else None})
    msg = "Готово! Ми напишемо на пошту, щойно товар з'явиться."
    if _wants_json(request):
        return JsonResponse({"ok": True, "message": msg})
    messages.success(request, msg)
    return redirect(product.get_absolute_url())


# ---------------------------------------------------------------------------
# Generated images
# ---------------------------------------------------------------------------
def _svg(content: str) -> HttpResponse:
    resp = HttpResponse(content, content_type="image/svg+xml")
    patch_cache_control(resp, public=True, max_age=60 * 60 * 24 * 30, immutable=True)
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return resp


@require_GET
def part_svg(request, design_id, color_id):
    part = Part.objects.filter(design_id=design_id).only("design_id", "name").first()
    color = Color.objects.filter(pk=color_id).first()
    if not part or not color:
        raise Http404
    return _svg(render_part_svg(part.design_id, part.name, color.rgb, color.is_transparent, color.finish))


@require_GET
def fig_svg(request, accent):
    accent = "#" + "".join(ch for ch in accent if ch in "0123456789abcdefABCDEF")[:6]
    return _svg(render_minifig_svg(accent if len(accent) == 7 else "#E3000B"))
