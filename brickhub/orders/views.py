from __future__ import annotations

import hmac
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from cart import services as cart_services
from core.utils import client_ip, normalize_phone

from . import shipping
from .forms import CheckoutForm, TrackForm
from .models import Order, Payment
from .payments import card_payments_enabled, card_provider
from .payments.liqpay import LiqPayError, LiqPayProvider
from .services import CheckoutError, change_status, delivery_cost_for, place_order

logger = logging.getLogger("brickhub")


def _initial(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    return {"first_name": user.first_name, "last_name": user.last_name, "phone": user.phone, "email": user.email,
            "city": user.city, "city_ref": user.city_ref, "np_warehouse": user.np_warehouse,
            "np_warehouse_ref": user.np_warehouse_ref, "address": user.address, "postal_code": user.postal_code}


def checkout(request):
    cart = cart_services.get_cart(request)
    summary = cart_services.summarize(cart, user=request.user)
    if not summary.count:
        messages.info(request, "Кошик порожній — додайте товари, щоб оформити замовлення.")
        return redirect("cart:detail")
    form = CheckoutForm(request.POST or None, initial=_initial(request))
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = request.user if request.user.is_authenticated else None
        if not user and data.get("create_account"):
            User = get_user_model()
            if User.objects.filter(email__iexact=data["email"]).exists():
                form.add_error("email", "Акаунт із цією поштою вже існує — увійдіть, щоб оформити замовлення.")
            else:
                try:
                    validate_password(data["password"])
                except ValidationError as exc:
                    form.add_error("password", exc)
        if not form.errors:
            try:
                with transaction.atomic():
                    if not user and data.get("create_account"):
                        user = get_user_model().objects.create_user(
                            email=data["email"], password=data["password"], first_name=data["first_name"],
                            last_name=data["last_name"], phone=data["phone"])
                    order = place_order(request, cart, data, user=user)
            except CheckoutError as exc:
                messages.error(request, str(exc))
                return redirect("cart:detail")
            if user and not request.user.is_authenticated:
                login(request, user, backend="accounts.backends.EmailBackend")
            if user:
                fields = {"phone": data["phone"], "city": data["city"], "city_ref": data.get("city_ref", ""),
                          "np_warehouse": data.get("np_warehouse", ""), "address": data.get("address", ""),
                          "postal_code": data.get("postal_code", "")}
                for key, value in fields.items():
                    if value and not getattr(user, key):
                        setattr(user, key, value)
                user.save()
            request.session["last_order"] = order.number
            if order.payment_method == Order.PAYMENT_CARD:
                return redirect(reverse("orders:pay", args=[order.number]) + f"?t={order.access_token}")
            return redirect(reverse("orders:success", args=[order.number]) + f"?t={order.access_token}")
    free_delivery = delivery_cost_for(summary.total, Order.DELIVERY_NP_WAREHOUSE) == 0
    return render(request, "orders/checkout.html", {
        "form": form, "summary": summary, "np_live": shipping.nova_poshta_enabled(),
        "card_enabled": card_payments_enabled(), "free_delivery": free_delivery,
        "crumbs": [("Кошик", reverse("cart:detail")), ("Оформлення замовлення", None)],
        "seo": {"title": "Оформлення замовлення", "noindex": True},
    })


def _order_for(request, number) -> Order:
    order = get_object_or_404(Order.objects.prefetch_related("items", "events"), number=number)
    token = request.GET.get("t", "")
    allowed = (
        (token and hmac.compare_digest(token, order.access_token))
        or (request.user.is_authenticated and (order.user_id == request.user.id or request.user.is_staff))
        or request.session.get("last_order") == order.number
    )
    if not allowed:
        raise Http404
    return order


def success(request, number):
    order = _order_for(request, number)
    return render(request, "orders/success.html", {
        "order": order, "card_enabled": card_payments_enabled(),
        "crumbs": [("Замовлення", None)], "seo": {"title": f"Замовлення {order.number}", "noindex": True},
    })


def pay(request, number):
    order = _order_for(request, number)
    provider = card_provider()
    if order.payment_method != Order.PAYMENT_CARD or order.payment_status == "paid":
        return redirect(reverse("orders:success", args=[order.number]) + f"?t={order.access_token}")
    if provider is None:
        messages.error(request, "Онлайн-оплата зараз недоступна. Менеджер зв'яжеться з вами щодо оплати.")
        return redirect(reverse("orders:success", args=[order.number]) + f"?t={order.access_token}")
    result_url = request.build_absolute_uri(reverse("orders:success", args=[order.number])) + \
        f"?t={order.access_token}&paid=1"
    server_url = request.build_absolute_uri(reverse("orders:liqpay_callback"))
    form = provider.checkout_form(order, result_url=result_url, server_url=server_url)
    Payment.objects.get_or_create(order=order, provider=provider.code, status="created",
                                  defaults={"amount": order.total})
    return render(request, "orders/pay.html", {"order": order, "form": form, "provider": provider,
                                               "seo": {"title": "Оплата замовлення", "noindex": True}})


@csrf_exempt
@require_POST
def liqpay_callback(request):
    provider = LiqPayProvider()
    try:
        payload = provider.parse_callback(request.POST.get("data", ""), request.POST.get("signature", ""))
    except LiqPayError as exc:
        logger.warning("Rejected LiqPay callback: %s", exc)
        return HttpResponseBadRequest("invalid signature")
    order = Order.objects.filter(number=payload.get("order_id", "")).first()
    if not order:
        return HttpResponseBadRequest("unknown order")
    payment = Payment.objects.filter(order=order, provider=provider.code).first() or Payment(
        order=order, provider=provider.code, amount=order.total)
    payment.payload = payload
    payment.external_id = str(payload.get("payment_id", ""))[:120]
    status = payload.get("status", "")
    if provider.is_success(payload) and provider.amount_matches(payload, order):
        payment.status = "success"
        payment.save()
        if order.payment_status != "paid":
            change_status(order, Order.STATUS_PAID, note="Оплату отримано через LiqPay")
    elif status in ("failure", "error"):
        payment.status = "failure"
        payment.save()
        Order.objects.filter(pk=order.pk).update(payment_status="failed")
    elif status == "reversed":
        payment.status = "reversed"
        payment.save()
        Order.objects.filter(pk=order.pk).update(payment_status="refunded")
    else:
        payment.status = "pending"
        payment.save()
    return HttpResponse("ok")


def track(request):
    form = TrackForm(request.POST or request.GET or None)
    order = None
    carrier = None
    if form.is_bound and form.is_valid():
        key = f"track:{client_ip(request)}"
        tries = cache.get(key, 0)
        if tries > 20:
            messages.error(request, "Забагато спроб. Спробуйте за кілька хвилин.")
        else:
            cache.set(key, tries + 1, 600)
            number = form.cleaned_data["number"].strip().upper()
            contact = form.cleaned_data["contact"].strip().lower()
            candidate = Order.objects.filter(number=number).prefetch_related("items", "events").first()
            if candidate and (contact == candidate.email.lower() or
                              (normalize_phone(contact) and normalize_phone(contact) == candidate.phone)):
                order = candidate
                if order.tracking_number and order.is_nova_poshta and shipping.nova_poshta_enabled():
                    try:
                        carrier = shipping.NovaPoshtaClient().track(order.tracking_number, order.phone)
                    except shipping.NovaPoshtaError as exc:
                        carrier = {"error": str(exc)}
            else:
                messages.error(request, "Замовлення не знайдено. Перевірте номер і телефон / e-mail.")
    return render(request, "orders/track.html", {
        "form": form, "order": order, "carrier": carrier, "crumbs": [("Відстеження замовлення", None)],
        "seo": {"title": "Відстеження замовлення", "noindex": True},
    })


# ---------------------------------------------------------------------------
# Nova Poshta lookups (proxied so the API key never reaches the browser)
# ---------------------------------------------------------------------------
def _np_guard(request):
    if not shipping.nova_poshta_enabled():
        return JsonResponse({"enabled": False, "items": []})
    key = f"np-rate:{client_ip(request)}"
    hits = cache.get(key, 0)
    if hits > 120:
        return JsonResponse({"enabled": True, "items": [], "error": "Забагато запитів"}, status=429)
    cache.set(key, hits + 1, 60)
    return None


@require_GET
def np_cities(request):
    blocked = _np_guard(request)
    if blocked:
        return blocked
    try:
        items = shipping.NovaPoshtaClient().search_cities(request.GET.get("q", ""))
    except shipping.NovaPoshtaError as exc:
        return JsonResponse({"enabled": True, "items": [], "error": str(exc)}, status=502)
    return JsonResponse({"enabled": True, "items": items})


@require_GET
def np_warehouses(request):
    blocked = _np_guard(request)
    if blocked:
        return blocked
    kind = "postomat" if request.GET.get("type") == "postomat" else "branch"
    try:
        items = shipping.NovaPoshtaClient().warehouses(request.GET.get("city_ref", ""), request.GET.get("q", ""),
                                                       kind=kind)
    except shipping.NovaPoshtaError as exc:
        return JsonResponse({"enabled": True, "items": [], "error": str(exc)}, status=502)
    return JsonResponse({"enabled": True, "items": items})
