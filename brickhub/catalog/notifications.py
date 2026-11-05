"""'Notify me when it is back in stock' e-mails."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger("brickhub")


def notify_back_in_stock(product_id: int) -> int:
    from .models import Product, StockNotification

    pending = list(StockNotification.objects.filter(product_id=product_id, notified_at__isnull=True))
    if not pending:
        return 0
    product = Product.objects.filter(pk=product_id, is_active=True).select_related("inventory").first()
    if not product or not product.in_stock:
        return 0
    sent = 0
    url = settings.SHOP["SITE_URL"].rstrip("/") + product.get_absolute_url()
    for sub in pending:
        context = {"product": product, "url": url, "shop": settings.SHOP}
        try:
            send_mail(
                subject=f"{product.title} знову в наявності — {settings.SHOP['NAME']}",
                message=render_to_string("emails/back_in_stock.txt", context),
                from_email=None,
                recipient_list=[sub.email],
                html_message=render_to_string("emails/back_in_stock.html", context),
            )
        except Exception:  # do not lose the subscription if SMTP is down
            logger.exception("Back-in-stock e-mail to %s failed", sub.email)
            continue
        sub.notified_at = timezone.now()
        sub.save(update_fields=["notified_at"])
        sent += 1
    return sent
