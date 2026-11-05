from __future__ import annotations

import re

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from catalog.models import Color, Product

from . import services
from .models import CartItem, PromoCode


def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch"


def _qty(value, default=1):
    try:
        return max(0, min(int(value), 100000))
    except (TypeError, ValueError):
        return default


def cart_detail(request):
    cart = services.get_cart(request)
    summary = services.summarize(cart, user=request.user)
    in_cart = [i.product_id for i in summary.items]
    suggestions = []
    if summary.items:
        theme_ids = {i.product.theme_id for i in summary.items if i.product.theme_id}
        suggestions = list(Product.objects.active().in_stock().filter(
            Q(theme_id__in=theme_ids, kind="minifig") | Q(is_bestseller=True)).exclude(pk__in=in_cart)
            .with_related().order_by("-sold_count", "-is_featured")[:8])
    return render(request, "cart/cart.html", {"cart": cart, "summary": summary, "suggestions": suggestions,
                                              "crumbs": [("Кошик", None)],
                                              "seo": {"title": "Кошик", "noindex": True}})


def _cart_payload(request, message="", ok=True, status=200):
    cart = services.get_cart(request)
    summary = services.summarize(cart, user=request.user)
    html = render_to_string("cart/_mini.html", {"summary": summary}, request=request)
    return JsonResponse({"ok": ok, "message": message, "count": summary.count, "total": f"{summary.total:.2f}",
                         "mini": html}, status=status)


@require_POST
def add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product"))
    qty = _qty(request.POST.get("quantity"), 1) or 1
    cart = services.get_cart(request, create=True)
    try:
        item, added = services.add_product(cart, product, qty)
    except services.CartError as exc:
        if _wants_json(request):
            return _cart_payload(request, str(exc), ok=False, status=400)
        messages.error(request, str(exc))
        return redirect(request.POST.get("next") or product.get_absolute_url())
    msg = f"Додано в кошик: {product.title}" + (f" — {added} шт." if added > 1 else "")
    if added < qty:
        msg += f" (доступно лише {product.stock} шт.)"
    if _wants_json(request):
        return _cart_payload(request, msg)
    messages.success(request, msg)
    return redirect(request.POST.get("next") or "cart:detail")


@require_POST
def update(request, item_id):
    cart = services.get_cart(request)
    item = get_object_or_404(CartItem.objects.select_related("product__inventory"), pk=item_id, cart=cart)
    services.set_quantity(item, _qty(request.POST.get("quantity"), item.quantity))
    if _wants_json(request):
        return _cart_payload(request)
    return redirect("cart:detail")


@require_POST
def remove(request, item_id):
    cart = services.get_cart(request)
    CartItem.objects.filter(pk=item_id, cart=cart).delete()
    if _wants_json(request):
        return _cart_payload(request, "Товар прибрано з кошика")
    messages.info(request, "Товар прибрано з кошика")
    return redirect("cart:detail")


@require_POST
def clear(request):
    cart = services.get_cart(request)
    if cart:
        cart.items.all().delete()
        cart.promo = None
        cart.save(update_fields=["promo"])
    messages.info(request, "Кошик очищено")
    return redirect("cart:detail")


@require_POST
def promo(request):
    cart = services.get_cart(request, create=True)
    if request.POST.get("action") == "remove":
        cart.promo = None
        cart.save(update_fields=["promo"])
        messages.info(request, "Промокод прибрано")
        return redirect("cart:detail")
    code = (request.POST.get("code") or "").strip().upper()
    promo_code = PromoCode.objects.filter(code=code).first() if code else None
    if not promo_code:
        messages.error(request, "Такого промокоду не знайдено")
        return redirect("cart:detail")
    items = [i for i in cart.items.select_related("product__inventory") if i.product.is_active and i.product.in_stock]
    error = promo_code.validate_for(items, user=request.user)
    if error:
        messages.error(request, error)
        return redirect("cart:detail")
    cart.promo = promo_code
    cart.save(update_fields=["promo"])
    messages.success(request, f"Промокод {promo_code.code} застосовано: {promo_code.label}")
    return redirect("cart:detail")


# ---------------------------------------------------------------------------
# Quick order: paste a list of parts ("3001 Red 10")
# ---------------------------------------------------------------------------
LINE_SPLIT = re.compile(r"[\s,;\t]+")


def _find_color(spec: str):
    spec = spec.strip()
    if not spec:
        return None
    if spec.isdigit():
        return Color.objects.filter(bricklink_id=int(spec)).first()
    return Color.objects.filter(Q(name__iexact=spec) | Q(name_uk__iexact=spec) | Q(lego_name__iexact=spec)).first()


def parse_quick_order(text: str, limit: int = 300) -> list[dict]:
    rows = []
    for raw in text.splitlines()[:limit]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens = [t for t in LINE_SPLIT.split(line) if t]
        number, qty, color_spec = tokens[0], 1, ""
        rest = tokens[1:]
        if rest and rest[-1].isdigit():
            qty = int(rest[-1])
            rest = rest[:-1]
        color_spec = " ".join(rest)
        row = {"line": line, "number": number, "qty": max(1, min(qty, 100000)), "product": None, "error": ""}
        color = _find_color(color_spec) if color_spec else None
        if color_spec and not color:
            row["error"] = f"Колір «{color_spec}» не знайдено"
            rows.append(row)
            continue
        qs = Product.objects.active().select_related("inventory", "color", "part")
        product = None
        if color:
            product = qs.filter(kind="part", part__design_id__iexact=number, color=color).order_by("condition").first()
            if not product:
                product = qs.filter(kind="part", color=color, part__elements__element_id=number).first()
        else:
            product = (qs.filter(sku__iexact=number).first()
                       or qs.filter(kind="set", lego_set__number__iexact=number if "-" in number else f"{number}-1",
                                    condition="new").first()
                       or qs.filter(kind="minifig", minifigure__fig_number__iexact=number).first()
                       or qs.filter(kind="minifig", minifigure__bricklink_id__iexact=number).first()
                       or qs.filter(kind="part", part__elements__element_id=number).first())
            if not product:
                variants = qs.filter(kind="part", part__design_id__iexact=number)
                if variants.count() == 1:
                    product = variants.first()
                elif variants.exists():
                    row["error"] = "Вкажіть колір — ця деталь є в кількох кольорах"
        if product:
            row["product"] = product
            if not product.in_stock:
                row["error"] = "Немає в наявності"
            elif product.stock < row["qty"]:
                row["error"] = f"Доступно лише {product.stock} шт."
        elif not row["error"]:
            row["error"] = "Не знайдено в асортименті"
        rows.append(row)
    return rows


def quick_order(request):
    text = request.POST.get("lines", "") if request.method == "POST" else request.GET.get("lines", "")
    rows = parse_quick_order(text) if text else []
    if request.method == "POST" and request.POST.get("action") == "add":
        cart = services.get_cart(request, create=True)
        added = 0
        for row in rows:
            product = row["product"]
            if product and product.in_stock:
                try:
                    services.add_product(cart, product, row["qty"])
                    added += 1
                except services.CartError:
                    pass
        if added:
            messages.success(request, f"Додано позицій у кошик: {added}")
            return redirect("cart:detail")
        messages.error(request, "Жодну позицію не вдалося додати")
    ok = sum(1 for r in rows if r["product"] and not r["error"])
    total = sum((r["product"].price * min(r["qty"], r["product"].stock)) for r in rows
                if r["product"] and r["product"].in_stock)
    return render(request, "cart/quick_order.html", {
        "text": text, "rows": rows, "ok_count": ok, "rows_total": total,
        "crumbs": [("Швидке замовлення деталей", None)],
        "seo": {"title": "Швидке замовлення деталей LEGO за списком", "noindex": True},
    })
