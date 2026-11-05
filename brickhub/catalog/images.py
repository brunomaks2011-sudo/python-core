"""Uploaded photo processing: validation, downscaling and WebP thumbnails."""
from __future__ import annotations

import io
import logging
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("brickhub")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1600
THUMB_SIDE = 600
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def validate_image_file(f) -> None:
    """Raise ValidationError unless ``f`` is a real, reasonably sized image."""
    if f.size > MAX_UPLOAD_BYTES:
        raise ValidationError("Файл завеликий (максимум 8 МБ).")
    pos = f.tell() if hasattr(f, "tell") else 0
    try:
        with Image.open(f) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("Це не схоже на зображення (підтримуються JPG, PNG, WEBP).")
    finally:
        try:
            f.seek(pos)
        except Exception:  # pragma: no cover
            pass
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Непідтримуваний формат зображення.")


def _encode(img: Image.Image, fmt: str = "WEBP", quality: int = 84) -> bytes:
    buf = io.BytesIO()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    img.save(buf, fmt, quality=quality, method=4)
    return buf.getvalue()


def process_upload(photo) -> bool:
    """Downscale the original to MAX_SIDE and create a WebP thumbnail.

    Returns True when the model fields changed and need saving.
    """
    try:
        photo.image.open("rb")
        with Image.open(photo.image) as src:
            img = ImageOps.exif_transpose(src)
            img.load()
    except Exception:  # broken file – keep it, but do not crash the request
        logger.exception("Cannot process product photo %s", photo.pk)
        return False
    stem = PurePosixPath(photo.image.name).stem
    if max(img.size) > MAX_SIDE:
        big = img.copy()
        big.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        old_name = photo.image.name
        photo.image.save(f"{stem}.webp", ContentFile(_encode(big)), save=False)
        if old_name != photo.image.name:
            photo.image.storage.delete(old_name)
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    photo.thumbnail.save(f"{stem}-thumb.webp", ContentFile(_encode(thumb, quality=80)), save=False)
    return True
