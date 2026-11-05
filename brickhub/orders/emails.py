from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger("brickhub")


def _site(path: str) -> str:
    return settings.SHOP["SITE_URL"].rstrip("/") + path


def _send(subject, template, context, recipients):
    if not recipients:
        return
    try:
        send_mail(subject=subject, message=render_to_string(f"emails/{template}.txt", context), from_email=None,
                  recipient_list=recipients, html_message=render_to_string(f"emails/{template}.html", context))
    except Exception:
        logger.exception("E-mail '%s' to %s failed", subject, recipients)


def send_new_order_emails(order_id: int):
    from .models import Order

    order = Order.objects.prefetch_related("items").get(pk=order_id)
    link = _site(reverse("orders:success", args=[order.number]) + f"?t={order.access_token}")
    ctx = {"order": order, "link": link, "shop": settings.SHOP}
    _send(f"Замовлення {order.number} прийнято — {settings.SHOP['NAME']}", "order_created", ctx, [order.email])
    admin_link = _site(reverse("panel:order_detail", args=[order.pk]))
    _send(f"Нове замовлення {order.number} на {order.total} ₴", "order_admin",
          {**ctx, "admin_link": admin_link}, settings.SHOP["ORDER_NOTIFY_EMAILS"])


def send_status_email(order_id: int, event_id: int):
    from .models import Order, OrderStatusEvent

    order = Order.objects.get(pk=order_id)
    event = OrderStatusEvent.objects.get(pk=event_id)
    link = _site(reverse("orders:success", args=[order.number]) + f"?t={order.access_token}")
    _send(f"Замовлення {order.number}: {order.get_status_display().lower()}", "order_status",
          {"order": order, "event": event, "link": link, "shop": settings.SHOP}, [order.email])
