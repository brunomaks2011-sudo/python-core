import logging
import urllib.request
from pathlib import PurePosixPath
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from catalog.models import ProductImage

logger = logging.getLogger("brickhub")


class Command(BaseCommand):
    help = "Завантажує зовнішні зображення товарів у локальне сховище (media/) для швидкості та незалежності."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **opts):
        qs = ProductImage.objects.filter(image="").exclude(external_url="").select_related("product")
        if opts["limit"]:
            qs = qs[: opts["limit"]]
        ok = failed = 0
        for photo in qs:
            try:
                req = urllib.request.Request(photo.external_url, headers={"User-Agent": "BrickHubShop/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - admin supplied https URL
                    if resp.status != 200 or not resp.headers.get("Content-Type", "").startswith("image/"):
                        raise ValueError("not an image")
                    data = resp.read(10 * 1024 * 1024)
                name = PurePosixPath(urlparse(photo.external_url).path).name or "image.jpg"
                photo.image.save(name, ContentFile(data), save=False)
                photo.save()
                ok += 1
            except Exception as exc:  # keep the external URL as a fallback
                failed += 1
                logger.warning("Cannot download %s: %s", photo.external_url, exc)
        self.stdout.write(self.style.SUCCESS(f"Завантажено: {ok}, помилок: {failed}"))
