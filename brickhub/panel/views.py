"""Staff-only admin panel (/panel/)."""
from __future__ import annotations

import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cart.models import PromoCode
from catalog.models import (
    Category, Color, Element, Inventory, InventoryMovement, LegoSet, Minifigure, Part, Product, ProductImage,
    Review, StockNotification, Theme,
)
from catalog.notifications import notify_back_in_stock
from orders.models import Order, OrderItem
from orders.services import change_status

from . import forms as pf
from .importers import ImportFileError, TEMPLATES, export_rows, read_table, run_import, template_xlsx

staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="accounts:login")
superuser_required = user_passes_test(lambda u: u.is_active and u.is_superuser, login_url="accounts:login")
REVENUE_STATUSES = [s for s, _ in Order.STATUSES if s not in (Order.STATUS_CANCELLED, Order.STATUS_RETURNED)]


def _page(request, qs, per=50):
    return Paginator(qs, per).get_page(request.GET.get("page"))


# ---------------------------------------------------------------------------
# Dashboard & statistics
# ---------------------------------------------------------------------------
@staff_required
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()
    orders = Order.objects.filter(status__in=REVENUE_STATUSES)

    def window(days):
        since = now - timedelta(days=days)
        agg = orders.filter(created_at__gte=since).aggregate(total=Sum("total"), n=Count("id"))
        return {"total": agg["total"] or Decimal("0"), "n": agg["n"],
                "avg": (agg["total"] or 0) / agg["n"] if agg["n"] else Decimal("0")}

    start = today - timedelta(days=29)
    daily_rows = (orders.filter(created_at__date__gte=start).annotate(day=TruncDate("created_at"))
                  .values("day").annotate(total=Sum("total"), n=Count("id")))
    by_day = {r["day"]: r for r in daily_rows}
    days = []
    peak = max([r["total"] for r in by_day.values()] or [Decimal("0")]) or Decimal("1")
    for i in range(30):
        d = start + timedelta(days=i)
        r = by_day.get(d, {"total": Decimal("0"), "n": 0})
        days.append({"date": d, "total": r["total"] or Decimal("0"), "n": r["n"],
                     "pct": float((r["total"] or 0) / peak * 100) if peak else 0})
    status_counts = dict(Order.objects.values_list("status").annotate(n=Count("id")))
    max_n = max(status_counts.values() or [1]) or 1
    statuses = [{"code": c, "label": label, "n": status_counts.get(c, 0),
                 "pct": round(status_counts.get(c, 0) / max_n * 100)} for c, label in Order.STATUSES]
    top = (OrderItem.objects.filter(order__status__in=REVENUE_STATUSES, order__created_at__gte=now - timedelta(days=30))
           .values("sku", "title").annotate(qty=Sum("quantity"), revenue=Sum(F("unit_price") * F("quantity")))
           .order_by("-revenue")[:10])
    low_stock = (Product.objects.active().filter(inventory__quantity__lte=F("inventory__low_stock_threshold"))
                 | Product.objects.active().exclude(kind="part").filter(inventory__quantity__lte=2))
    low_stock = low_stock.select_related("inventory").order_by("inventory__quantity")[:12]
    kinds = dict(Product.objects.active().values_list("kind").annotate(n=Count("id")))
    stock_value = Product.objects.active().aggregate(v=Sum(F("price") * F("inventory__quantity")))["v"] or 0
    User = get_user_model()
    ctx = {
        "w1": window(1), "w7": window(7), "w30": window(30), "days": days, "statuses": statuses, "top": top,
        "low_stock": low_stock, "kinds": kinds, "stock_value": stock_value,
        "recent_orders": Order.objects.order_by("-created_at")[:8],
        "new_users": User.objects.filter(date_joined__gte=now - timedelta(days=30)).count(),
        "users_total": User.objects.count(),
        "pending_notifications": StockNotification.objects.filter(notified_at__isnull=True).count(),
        "pending_reviews": Review.objects.filter(is_published=False).count(),
        "open_orders": Order.objects.filter(status__in=Order.OPEN_STATUSES).count(),
        "section": "dashboard",
    }
    return render(request, "panel/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
@staff_required
def product_list(request):
    qs = Product.objects.select_related("inventory", "color", "part", "lego_set", "minifigure", "category",
                                        "theme").prefetch_related("images")
    q = request.GET.get("q", "").strip()
    if q:
        for tok in q.lower().split():
            qs = qs.filter(search_text__icontains=tok)
    kind = request.GET.get("kind", "")
    if kind:
        qs = qs.filter(kind=kind)
    stock = request.GET.get("stock", "")
    if stock == "out":
        qs = qs.filter(inventory__quantity=0)
    elif stock == "low":
        qs = qs.filter(inventory__quantity__gt=0, inventory__quantity__lte=3)
    status = request.GET.get("status", "")
    if status == "hidden":
        qs = qs.filter(is_active=False)
    elif status == "active":
        qs = qs.filter(is_active=True)
    photo = request.GET.get("photo", "")
    if photo == "none":
        qs = qs.filter(images__isnull=True)
    elif photo == "has":
        qs = qs.filter(images__isnull=False).distinct()
    cat = request.GET.get("category", "")
    if cat:
        c = Category.objects.filter(slug=cat).first()
        if c:
            qs = qs.filter(category_id__in=c.descendant_ids())
    order = request.GET.get("order", "-updated_at")
    if order not in ("-updated_at", "price", "-price", "title", "inventory__quantity", "-inventory__quantity",
                     "-sold_count", "sku"):
        order = "-updated_at"
    qs = qs.order_by(order)
    page = _page(request, qs, 50)
    return render(request, "panel/products.html", {
        "page": page, "q": q, "kind": kind, "stock": stock, "status": status, "order": order, "category": cat,
        "photo": photo, "no_photo_count": Product.objects.filter(images__isnull=True).count(),
        "category_groups": _category_groups(), "kinds": Product.KINDS, "section": "products",
        "total": page.paginator.count,
    })


def _category_groups() -> list[tuple[Category, list[Category]]]:
    """[(top-level section, [its subcategories at any depth])] in menu order — for grouped <select>s."""
    cats = list(Category.objects.order_by("sort_order", "name"))
    by_pk = {c.pk: c for c in cats}

    def top(c):
        seen = set()
        while c.parent_id and c.parent_id in by_pk and c.pk not in seen:
            seen.add(c.pk)
            c = by_pk[c.parent_id]
        return c

    groups = {c.pk: (c, []) for c in cats if not c.parent_id}
    for c in cats:
        if c.parent_id:
            root = top(c)
            if root.pk in groups:
                groups[root.pk][1].append(c)
    return list(groups.values())


@staff_required
@require_POST
def product_bulk(request):
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    action = request.POST.get("action")
    qs = Product.objects.filter(pk__in=ids)
    if not ids:
        messages.error(request, "Оберіть товари")
    elif action == "activate":
        n = qs.update(is_active=True)
        messages.success(request, f"Показано на сайті: {n}")
    elif action == "deactivate":
        n = qs.update(is_active=False)
        messages.success(request, f"Приховано: {n}")
    elif action == "delete":
        used = set(OrderItem.objects.filter(product_id__in=ids).values_list("product_id", flat=True))
        deletable = qs.exclude(pk__in=used)
        n = deletable.count()
        deletable.delete()
        if used:
            Product.objects.filter(pk__in=used).update(is_active=False)
            messages.warning(request, f"{len(used)} товар(ів) є в замовленнях — їх приховано замість видалення.")
        messages.success(request, f"Видалено: {n}")
    elif action == "set_category":
        raw = request.POST.get("category", "")
        cat = Category.objects.filter(pk=int(raw)).first() if raw.isdigit() else None
        if cat is None:
            messages.error(request, "Оберіть категорію, у яку перенести товари")
        else:
            n = 0
            for product in qs.exclude(category=cat).select_related("lego_set", "part", "color", "minifigure", "theme"):
                product.category = cat
                product.save()  # also refreshes the search index (it includes the category name)
                n += 1
            messages.success(request, f"Перенесено в «{cat}»: {n}")
    elif action in ("set_new", "unset_new", "set_featured", "unset_featured", "set_bestseller", "unset_bestseller"):
        field = {"new": "is_new", "featured": "is_featured", "bestseller": "is_bestseller"}[action.split("_", 1)[1]]
        n = qs.update(**{field: action.startswith("set_")})
        messages.success(request, f"Оновлено: {n}")
    return redirect(request.POST.get("next") or "panel:products")


@staff_required
@require_POST
def product_quick_update(request, pk):
    """Inline price / stock edit from the product table."""
    product = get_object_or_404(Product.objects.select_related("inventory"), pk=pk)
    errors = {}
    try:
        price = Decimal(request.POST.get("price", "").replace(",", "."))
        if price <= 0:
            raise ValueError
    except Exception:
        price = None
        if request.POST.get("price"):
            errors["price"] = "Невірна ціна"
    try:
        qty = int(request.POST.get("quantity", ""))
        if qty < 0:
            raise ValueError
    except (TypeError, ValueError):
        qty = None
        if request.POST.get("quantity"):
            errors["quantity"] = "Невірна кількість"
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    if price is not None and price != product.price:
        product.price = price
        product.save(update_fields=["price", "updated_at"])
    inv = product.inventory
    if qty is not None and qty != inv.quantity:
        change = qty - inv.quantity
        inv.quantity = qty
        inv.save()
        InventoryMovement.objects.create(inventory=inv, change=change, quantity_after=qty, reason="manual",
                                         user=request.user)
    return JsonResponse({"ok": True, "price": f"{product.price:.2f}", "quantity": inv.quantity})


@staff_required
def product_edit(request, pk=None):
    product = get_object_or_404(Product.objects.select_related("inventory", "lego_set", "part", "minifigure"),
                                pk=pk) if pk else None
    initial = {}
    if not product:
        initial = {"kind": request.GET.get("kind", "set"), "condition": "new", "is_active": True}
        # "add the same part in another colour" pre-fills the number and category
        for key in ("design_id", "set_number", "fig_number"):
            if request.GET.get(key):
                initial[key] = request.GET[key][:40]
        if (request.GET.get("category") or "").isdigit():
            initial["category"] = int(request.GET["category"])
    form = pf.ProductForm(request.POST or None, instance=product, initial=initial)
    form.user = request.user
    images_form = pf.ImagesForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and images_form.is_valid():
        product = form.save()
        for f in images_form.cleaned_data.get("images") or []:
            ProductImage.objects.create(product=product, image=f, alt=product.title,
                                        sort_order=product.images.count())
        url = images_form.cleaned_data.get("external_url")
        if url:
            ProductImage.objects.create(product=product, external_url=url, alt=product.title,
                                        sort_order=product.images.count())
        messages.success(request, f"Збережено: {product.title} ({product.sku})")
        if request.POST.get("then") == "new":
            return redirect(reverse("panel:product_new") + f"?kind={product.kind}")
        if request.POST.get("then") == "other_color" and product.part_id:
            return redirect(reverse("panel:product_new") + f"?kind=part&design_id={product.part.design_id}"
                            + (f"&category={product.category_id}" if product.category_id else ""))
        return redirect("panel:product_edit", pk=product.pk)
    movements = product.inventory.movements.select_related("user", "order")[:15] if product else []
    same_part = []
    if product and product.kind == "part" and product.part_id:
        same_part = list(Product.objects.filter(part_id=product.part_id).select_related("color", "inventory")
                         .prefetch_related("images").order_by("color__sort_order", "condition"))
    return render(request, "panel/product_form.html", {
        "form": form, "images_form": images_form, "product": product, "movements": movements, "same_part": same_part,
        "section": "products", "colors": Color.objects.filter(is_active=True).order_by("sort_order", "name"),
    })


@staff_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if OrderItem.objects.filter(product=product).exists():
        product.is_active = False
        product.save(update_fields=["is_active"])
        messages.warning(request, "Товар є в замовленнях, тому його приховано, а не видалено.")
        return redirect("panel:product_edit", pk=product.pk)
    title = product.title
    product.delete()
    messages.success(request, f"Видалено: {title}")
    return redirect("panel:products")


@staff_required
@require_POST
def image_action(request, pk):
    image = get_object_or_404(ProductImage, pk=pk)
    product = image.product
    action = request.POST.get("action")
    if action == "delete":
        if image.image:
            image.image.delete(save=False)
        if image.thumbnail:
            image.thumbnail.delete(save=False)
        image.delete()
        messages.success(request, "Фото видалено")
    elif action == "main":
        others = list(product.images.exclude(pk=image.pk))
        image.sort_order = 0
        image.save(update_fields=["sort_order"])
        for i, other in enumerate(others, start=1):
            if other.sort_order != i:
                other.sort_order = i
                other.save(update_fields=["sort_order"])
        messages.success(request, "Головне фото змінено")
    return redirect("panel:product_edit", pk=product.pk)


@staff_required
def catalog_lookup(request):
    """Auto-fill helper for the product form."""
    kind = request.GET.get("kind")
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"found": False})
    if kind in ("set", "accessory"):
        s = LegoSet.objects.filter(number__iexact=q if "-" in q else f"{q}-1").select_related("theme").first()
        if not s:
            return JsonResponse({"found": False, "message": "Номера немає в каталозі"})
        root = s.theme
        while root and root.parent_id and not root.is_primary:
            root = root.parent
        return JsonResponse({"found": True, "name": s.name, "year": s.year, "pieces": s.pieces,
                             "minifigs": s.minifigs_count, "age": s.age_min,
                             "theme_id": root.pk if root else None,
                             "theme": root.display_name if root else "",
                             "listings": list(Product.objects.filter(lego_set=s).values("pk", "sku", "condition"))})
    if kind == "part":
        p = Part.objects.filter(design_id__iexact=q).select_related("category").first()
        if not p:
            el = Element.objects.filter(element_id=q).select_related("part", "color").first()
            if el:
                return JsonResponse({"found": True, "design_id": el.part.design_id, "name": el.part.name,
                                     "name_uk": el.part.name_uk, "color_id": el.color_id,
                                     "category_id": el.part.category_id})
            return JsonResponse({"found": False, "message": "Деталі немає в каталозі"})
        return JsonResponse({"found": True, "design_id": p.design_id, "name": p.name, "name_uk": p.name_uk,
                             "category_id": p.category_id,
                             "listings": list(Product.objects.filter(part=p).values("pk", "sku", "color__name",
                                                                                    "condition"))})
    if kind == "minifig":
        m = Minifigure.objects.filter(Q(fig_number__iexact=q) | Q(bricklink_id__iexact=q)).first()
        if not m:
            return JsonResponse({"found": False, "message": "Мініфігурки немає в каталозі"})
        return JsonResponse({"found": True, "name": m.name, "year": m.year,
                             "theme_id": m.theme_id, "bricklink_id": m.bricklink_id})
    return JsonResponse({"found": False})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@staff_required
def order_list(request):
    qs = Order.objects.annotate(n_items=Sum("items__quantity")).order_by("-created_at")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) |
                       Q(last_name__icontains=q) | Q(tracking_number__icontains=q))
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    payment = request.GET.get("payment", "")
    if payment:
        qs = qs.filter(payment_method=payment)
    date_from, date_to = request.GET.get("from", ""), request.GET.get("to", "")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    page = _page(request, qs, 40)
    return render(request, "panel/orders.html", {
        "page": page, "q": q, "status": status, "payment": payment, "date_from": date_from, "date_to": date_to,
        "statuses": Order.STATUSES, "payments": Order.PAYMENT_METHODS, "section": "orders",
    })


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__product__inventory", "events__created_by",
                                                             "payments"), pk=pk)
    status_form = pf.OrderStatusForm(initial={"status": order.status})
    meta_form = pf.OrderMetaForm(instance=order)
    if request.method == "POST":
        if request.POST.get("form") == "status":
            status_form = pf.OrderStatusForm(request.POST)
            if status_form.is_valid():
                change_status(order, status_form.cleaned_data["status"], note=status_form.cleaned_data["note"],
                              by=request.user, notify=status_form.cleaned_data["notify"])
                messages.success(request, "Статус оновлено")
                return redirect("panel:order_detail", pk=order.pk)
        else:
            meta_form = pf.OrderMetaForm(request.POST, instance=order)
            if meta_form.is_valid():
                had_ttn = bool(Order.objects.filter(pk=order.pk).values_list("tracking_number", flat=True)[0])
                order = meta_form.save(commit=False)
                order.recalc()
                order.save()
                if order.tracking_number and not had_ttn and order.status in Order.OPEN_STATUSES:
                    change_status(order, Order.STATUS_SHIPPED, note=f"ТТН {order.tracking_number}",
                                  by=request.user)
                messages.success(request, "Збережено")
                return redirect("panel:order_detail", pk=order.pk)
    return render(request, "panel/order_detail.html", {
        "order": order, "status_form": status_form, "meta_form": meta_form, "section": "orders",
    })


@staff_required
def order_packing(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__product__inventory"), pk=pk)
    items = sorted(order.items.all(), key=lambda i: (
        (i.product.inventory.location if i.product_id and hasattr(i.product, "inventory") else "") or "ZZZ", i.sku))
    return render(request, "panel/order_packing.html", {"order": order, "items": items})


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@staff_required
def user_list(request):
    User = get_user_model()
    qs = User.objects.annotate(n_orders=Count("orders"), spent=Sum("orders__total")).order_by("-date_joined")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                       Q(phone__icontains=q))
    role = request.GET.get("role", "")
    if role == "staff":
        qs = qs.filter(is_staff=True)
    elif role == "blocked":
        qs = qs.filter(is_active=False)
    return render(request, "panel/users.html", {"page": _page(request, qs, 50), "q": q, "role": role,
                                                "section": "users"})


@staff_required
def user_detail(request, pk):
    User = get_user_model()
    target = get_object_or_404(User, pk=pk)
    form = pf.UserAdminForm(request.POST or None, instance=target)
    if not request.user.is_superuser:
        form.fields["is_staff"].disabled = True
    if target.is_superuser and not request.user.is_superuser:
        for f in form.fields.values():
            f.disabled = True
    if request.method == "POST" and form.is_valid():
        if target == request.user and not form.cleaned_data["is_active"]:
            messages.error(request, "Не можна заблокувати власний акаунт")
        else:
            form.save()
            messages.success(request, "Користувача оновлено")
            return redirect("panel:user_detail", pk=target.pk)
    return render(request, "panel/user_detail.html", {"target": target, "form": form, "section": "users",
                                                      "orders": target.orders.all()[:20]})


# ---------------------------------------------------------------------------
# Reviews & stock notifications
# ---------------------------------------------------------------------------
@staff_required
def review_list(request):
    qs = Review.objects.select_related("product", "user")
    if request.method == "POST":
        review = get_object_or_404(Review, pk=request.POST.get("id"))
        action = request.POST.get("action")
        if action == "delete":
            review.delete()
        else:
            review.is_published = action == "publish"
            review.save(update_fields=["is_published"])
            review.product.refresh_rating()
        messages.success(request, "Готово")
        return redirect("panel:reviews")
    return render(request, "panel/reviews.html", {"page": _page(request, qs, 40), "section": "reviews"})


@staff_required
def notification_list(request):
    if request.method == "POST":
        pid = request.POST.get("product")
        sent = notify_back_in_stock(int(pid)) if pid and pid.isdigit() else 0
        messages.success(request, f"Надіслано листів: {sent}")
        return redirect("panel:notifications")
    rows = (StockNotification.objects.filter(notified_at__isnull=True).values(
        "product_id", "product__title", "product__sku", "product__inventory__quantity")
        .annotate(n=Count("id")).order_by("-n"))
    return render(request, "panel/notifications.html", {"rows": rows, "section": "notifications",
                                                        "sent": StockNotification.objects.filter(
                                                            notified_at__isnull=False).count()})


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------
@staff_required
def import_view(request):
    form = pf.ImportForm(request.POST or None, request.FILES or None)
    report = None
    if request.method == "POST" and form.is_valid():
        dry_run = request.POST.get("mode") != "apply"
        try:
            rows = read_table(form.cleaned_data["file"])
            if not rows:
                raise ImportFileError("У файлі немає рядків з даними")
            report = run_import(rows, form.cleaned_data["kind"], dry_run=dry_run, user=request.user,
                                allow_new_catalog=form.cleaned_data["allow_new_catalog"])
            if not dry_run:
                messages.success(request, f"Імпорт завершено: створено {report.created}, оновлено {report.updated}, "
                                          f"помилок {report.errors}")
        except ImportFileError as exc:
            messages.error(request, str(exc))
    return render(request, "panel/import.html", {"form": form, "report": report, "templates": TEMPLATES,
                                                 "section": "import"})


@staff_required
def import_template(request, kind):
    if kind not in TEMPLATES:
        raise Http404
    resp = HttpResponse(template_xlsx(kind),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="brickhub-import-{kind}.xlsx"'
    return resp


class _Echo:
    def write(self, value):
        return value


@staff_required
def export_products(request):
    qs = Product.objects.all().order_by("kind", "sku")
    kind = request.GET.get("kind")
    if kind:
        qs = qs.filter(kind=kind)
    writer = csv.writer(_Echo())
    stream = (writer.writerow(row) for row in export_rows(qs))
    resp = StreamingHttpResponse(_with_bom(stream), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="brickhub-products-{timezone.localdate()}.csv"'
    return resp


def _with_bom(stream):
    yield "\ufeff"
    yield from stream


# ---------------------------------------------------------------------------
# Generic CRUD for reference data
# ---------------------------------------------------------------------------

CRUD = {
    "colors": {"model": Color, "form": pf.ColorForm, "title": "Кольори", "one": "колір",
               "columns": [("swatch", "Колір"), ("name", "Офіційна назва"), ("name_uk", "Українською"),
                           ("bricklink_id", "BrickLink"), ("rebrickable_id", "Rebrickable"), ("rgb", "HEX"),
                           ("is_active", "У фільтрах")],
               "search": ["name", "name_uk"], "order": ("sort_order", "name")},
    "categories": {"model": Category, "form": pf.CategoryForm, "title": "Категорії", "one": "категорію",
                   "columns": [("name", "Назва"), ("parent", "Батьківська"), ("kind", "Тип"), ("slug", "Адреса"),
                               ("sort_order", "Порядок"), ("is_active", "Активна")],
                   "search": ["name", "slug"], "order": ("parent__sort_order", "sort_order")},
    "themes": {"model": Theme, "form": pf.ThemeForm, "title": "Серії LEGO", "one": "серію",
               "columns": [("display_name", "Назва"), ("parent", "Батьківська"), ("is_primary", "У меню наборів"),
                           ("show_in_minifigs", "У меню фігурок"), ("sort_order", "Порядок")],
               "search": ["name", "title"], "order": ("-is_primary", "-show_in_minifigs", "sort_order", "name")},
    "parts": {"model": Part, "form": pf.PartForm, "title": "Каталог деталей", "one": "деталь",
              "columns": [("design_id", "Design ID"), ("name", "Офіційна назва"), ("name_uk", "Українською"),
                          ("category", "Категорія")],
              "search": ["design_id", "name", "name_uk"], "order": ("design_id",)},
    "elements": {"model": Element, "form": pf.ElementForm, "title": "Element ID", "one": "елемент",
                 "columns": [("element_id", "Element ID"), ("part", "Деталь"), ("color", "Колір")],
                 "search": ["element_id", "part__design_id"], "order": ("element_id",)},
    "sets": {"model": LegoSet, "form": pf.LegoSetForm, "title": "Каталог наборів", "one": "набір",
             "columns": [("number", "Номер"), ("name", "Назва"), ("theme", "Серія"), ("year", "Рік"),
                         ("pieces", "Деталей"), ("age_min", "Вік")],
             "search": ["number", "name"], "order": ("-year", "number")},
    "minifigs": {"model": Minifigure, "form": pf.MinifigureForm, "title": "Каталог мініфігурок", "one": "мініфігурку",
                 "columns": [("fig_number", "Номер"), ("bricklink_id", "BrickLink"), ("name", "Назва"),
                             ("theme", "Серія"), ("year", "Рік")],
                 "search": ["fig_number", "bricklink_id", "name"], "order": ("fig_number",)},
    "promo": {"model": PromoCode, "form": pf.PromoCodeForm, "title": "Промокоди та знижки", "one": "промокод",
              "columns": [("code", "Код"), ("label", "Знижка"), ("scope", "Діє на"), ("used_count", "Використано"),
                          ("max_uses", "Ліміт"), ("valid_to", "Діє до"), ("is_active", "Активний")],
              "search": ["code", "description"], "order": ("-created_at",)},
}


def _cfg(key):
    cfg = CRUD.get(key)
    if not cfg:
        raise Http404
    return cfg


@staff_required
def crud_list(request, key):
    cfg = _cfg(key)
    qs = cfg["model"].objects.all().order_by(*cfg["order"])
    q = request.GET.get("q", "").strip()
    if q:
        cond = Q()
        for f in cfg["search"]:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)
    page = _page(request, qs, 60)
    rows = []
    for obj in page.object_list:
        cells = []
        for attr, _label in cfg["columns"]:
            if attr == "swatch":
                cells.append({"swatch": obj.hex, "trans": obj.is_transparent})
                continue
            value = getattr(obj, attr, "")
            display = getattr(obj, f"get_{attr}_display", None)
            if callable(display):
                value = display()
            cells.append({"value": value})
        rows.append({"obj": obj, "cells": cells})
    return render(request, "panel/crud_list.html", {"cfg": cfg, "key": key, "rows": rows, "page": page, "q": q,
                                                    "section": key})


@staff_required
def crud_edit(request, key, pk=None):
    cfg = _cfg(key)
    obj = get_object_or_404(cfg["model"], pk=pk) if pk else None
    form = cfg["form"](request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, "Збережено")
        return redirect("panel:crud_list", key=key)
    return render(request, "panel/crud_form.html", {"cfg": cfg, "key": key, "form": form, "obj": obj,
                                                    "section": key})


@staff_required
@require_POST
def crud_delete(request, key, pk):
    cfg = _cfg(key)
    obj = get_object_or_404(cfg["model"], pk=pk)
    try:
        obj.delete()
        messages.success(request, "Видалено")
    except Exception:
        messages.error(request, "Неможливо видалити: запис використовується товарами або замовленнями.")
    return redirect("panel:crud_list", key=key)
