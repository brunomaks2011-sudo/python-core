"""Uploaded photo processing: validation, downscaling, background removal and WebP thumbnails.

Every uploaded photo is kept twice: ``original`` — the photo as taken (downscaled, with its background) and
``image`` — what the shop shows: the same photo without a plain background when it could be removed
(see ``background.py``), otherwise the photo itself. The background can be brought back in the panel at any time.
"""
from __future__ import annotations

import io
import logging
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .background import has_transparency, remove_background

logger = logging.getLogger("brickhub")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1600
THUMB_SIDE = 600
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}


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
        img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    else:
        img.save(buf, fmt, quality=quality, method=4)
    return buf.getvalue()


def _load(field) -> Image.Image:
    field.open("rb")
    try:
        with Image.open(field) as src:
            img = ImageOps.exif_transpose(src)
            img.load()
    finally:
        field.close()
    if max(img.size) > MAX_SIDE:
        img = img.copy()
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return img


def _replace(field, name: str, data: bytes, keep: set[str]) -> None:
    """Save ``data`` into ``field`` under a new name and delete the file it replaces (unless still in use)."""
    old = field.name
    field.save(name, ContentFile(data), save=False)
    if old and old != field.name and old not in keep:
        field.storage.delete(old)


def _show(photo, img: Image.Image, stem: str) -> None:
    """Make ``img`` the shown photo and its thumbnail."""
    keep = {photo.original.name} if photo.original else set()
    _replace(photo.image, f"{stem}.webp", _encode(img, quality=86), keep)
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
    _replace(photo.thumbnail, f"{stem}-thumb.webp", _encode(thumb, quality=80), keep)


def _stem(photo) -> str:
    return PurePosixPath(photo.image.name or photo.original.name or "photo").stem.removesuffix("-thumb")


def _try_remove(photo, img: Image.Image) -> Image.Image:
    """The background-free version of ``img`` when possible; records the outcome on ``photo``."""
    try:
        result = remove_background(img)
    except Exception:  # an illustration must never break saving a product
        logger.exception("Background removal failed for photo %s", photo.pk)
        photo.background, photo.background_note = photo.BG_SKIPPED, "Не вдалося обробити фото"
        return img
    photo.background, photo.background_note = result.status, result.note[:160]
    return result.image if result.image is not None else img


def process_upload(photo) -> bool:
    """For a newly uploaded file: keep the original, remove a plain background, make the thumbnail.

    Returns True when the model fields changed and need saving.
    """
    try:
        img = _load(photo.image)
    except Exception:  # broken file – keep it, but do not crash the request
        logger.exception("Cannot process product photo %s", photo.pk)
        return False
    stem = _stem(photo)
    transparent = has_transparency(img)
    photo.original.save(f"{stem}.{'webp' if transparent else 'jpg'}",
                        ContentFile(_encode(img, "WEBP" if transparent else "JPEG", 88)), save=False)
    shown = img
    if settings.SHOP.get("REMOVE_PHOTO_BACKGROUND", True):
        shown = _try_remove(photo, img)
    elif transparent:
        photo.background, photo.background_note = photo.BG_TRANSPARENT, "Фон уже прозорий"
    _show(photo, shown, stem)
    return True


def remove_photo_background(photo) -> str:
    """Remove the background of a saved photo (again). Returns the outcome note."""
    if not (photo.original or photo.image):
        return "Фото за посиланням: фон прибирається лише для завантажених файлів"
    source = photo.original if photo.original else photo.image
    img = _load(source)
    stem = _stem(photo)
    if not photo.original:  # photos uploaded before backgrounds were removed: keep them as the original
        transparent = has_transparency(img)
        photo.original.save(f"{stem}.{'webp' if transparent else 'jpg'}",
                            ContentFile(_encode(img, "WEBP" if transparent else "JPEG", 88)), save=False)
    shown = _try_remove(photo, img)
    _show(photo, shown, stem)
    photo.save(update_fields=["image", "thumbnail", "original", "background", "background_note"])
    return photo.background_note or photo.get_background_display()


def restore_photo_background(photo) -> str:
    """Show the photo with its background again."""
    if not photo.original:
        return "Оригінал фото не збережено"
    img = _load(photo.original)
    _show(photo, img, _stem(photo))
    photo.background, photo.background_note = photo.BG_KEPT, "Фон повернуто"
    photo.save(update_fields=["image", "thumbnail", "background", "background_note"])
    return "Фон повернуто"


def photos_to_process():
    """Uploaded photos whose background was never looked at (e.g. added before this feature)."""
    from .models import ProductImage

    return ProductImage.objects.filter(background="").exclude(image="").select_related("product")
