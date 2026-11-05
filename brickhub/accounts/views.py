from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cart import services as cart_services
from catalog.models import Favorite, StockNotification
from orders.models import Order
from orders.services import change_status

from .forms import EmailChangeForm, LoginForm, ProfileForm, RegisterForm


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return default


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailBackend")
        messages.success(request, "Ласкаво просимо до BRICK HUB! Акаунт створено.")
        return redirect(_safe_next(request, reverse("accounts:dashboard")))
    return render(request, "accounts/register.html", {"form": form, "next": request.GET.get("next", ""),
                                                      "seo": {"title": "Реєстрація", "noindex": True}})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, reverse("accounts:dashboard")))
    form = LoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.user, backend="accounts.backends.EmailBackend")
        if not form.cleaned_data.get("remember"):
            request.session.set_expiry(0)
        messages.success(request, f"Вітаємо, {form.user.first_name or form.user.email}!")
        default = reverse("panel:dashboard") if form.user.is_staff else reverse("accounts:dashboard")
        return redirect(_safe_next(request, default))
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", ""),
                                                   "seo": {"title": "Вхід", "noindex": True}})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "Ви вийшли з акаунта")
    return redirect("core:home")


def _account_ctx(request, title, **extra):
    ctx = {"seo": {"title": title, "noindex": True},
           "crumbs": [("Особистий кабінет", reverse("accounts:dashboard")), (title, None)]}
    ctx.update(extra)
    return ctx


@login_required
def dashboard(request):
    orders = request.user.orders.prefetch_related("items")[:5]
    return render(request, "accounts/dashboard.html", _account_ctx(
        request, "Особистий кабінет", orders=orders, active="dashboard",
        favorites_count=Favorite.objects.filter(user=request.user).count(),
        open_orders=request.user.orders.filter(status__in=Order.OPEN_STATUSES).count(),
        orders_count=request.user.orders.count()))


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user, prefix="p")
    email_form = EmailChangeForm(request.user, request.POST or None, prefix="e") if request.POST.get(
        "form") == "email" else EmailChangeForm(request.user, prefix="e")
    if request.method == "POST":
        if request.POST.get("form") == "email":
            if email_form.is_valid():
                request.user.email = email_form.cleaned_data["email"]
                request.user.save(update_fields=["email"])
                messages.success(request, "Електронну пошту змінено")
                return redirect("accounts:profile")
            form = ProfileForm(instance=request.user, prefix="p")
        elif form.is_valid():
            form.save()
            messages.success(request, "Дані збережено")
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", _account_ctx(
        request, "Особисті дані", form=form, email_form=email_form, active="profile"))


@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Пароль змінено")
        return redirect("accounts:profile")
    return render(request, "accounts/password_change.html", _account_ctx(
        request, "Зміна пароля", form=form, active="profile"))


@login_required
def orders(request):
    qs = request.user.orders.prefetch_related("items")
    return render(request, "accounts/orders.html", _account_ctx(request, "Мої замовлення", orders=qs,
                                                                active="orders"))


@login_required
def order_detail(request, number):
    order = get_object_or_404(request.user.orders.prefetch_related("items__product", "events"), number=number)
    return render(request, "accounts/order_detail.html", _account_ctx(
        request, f"Замовлення {order.number}", order=order, active="orders",
        events=[e for e in order.events.all() if e.is_customer_visible]))


@login_required
@require_POST
def order_repeat(request, number):
    order = get_object_or_404(request.user.orders, number=number)
    cart = cart_services.get_cart(request, create=True)
    added, skipped = 0, []
    for item in order.items.select_related("product__inventory"):
        product = item.product
        if not product or not product.is_active or not product.in_stock:
            skipped.append(item.title)
            continue
        try:
            cart_services.add_product(cart, product, item.quantity)
            added += 1
        except cart_services.CartError:
            skipped.append(item.title)
    if added:
        messages.success(request, f"Додано в кошик позицій: {added}")
    if skipped:
        messages.warning(request, "Немає в наявності: " + ", ".join(skipped[:5]) + ("…" if len(skipped) > 5 else ""))
    return redirect("cart:detail")


@login_required
@require_POST
def order_cancel(request, number):
    order = get_object_or_404(request.user.orders, number=number)
    if not order.can_cancel:
        messages.error(request, "Це замовлення вже не можна скасувати онлайн — зв'яжіться з нами.")
    else:
        change_status(order, Order.STATUS_CANCELLED, note="Скасовано покупцем", by=request.user)
        messages.success(request, f"Замовлення {order.number} скасовано")
    return redirect("accounts:order_detail", number=order.number)


@login_required
def notifications(request):
    subs = StockNotification.objects.filter(email__iexact=request.user.email).select_related(
        "product", "product__inventory")
    return render(request, "accounts/notifications.html", _account_ctx(
        request, "Повідомлення про надходження", subs=subs, active="notifications"))


@login_required
@require_POST
def notification_delete(request, pk):
    StockNotification.objects.filter(pk=pk, email__iexact=request.user.email).delete()
    messages.info(request, "Підписку скасовано")
    return redirect("accounts:notifications")


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_context = {"seo": {"title": "Відновлення пароля", "noindex": True}}


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"
    extra_context = {"seo": {"title": "Відновлення пароля", "noindex": True}}


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    extra_context = {"seo": {"title": "Новий пароль", "noindex": True}}


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
    extra_context = {"seo": {"title": "Пароль змінено", "noindex": True}}
