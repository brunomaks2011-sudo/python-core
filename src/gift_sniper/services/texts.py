"""Message templates (HTML parse mode). Every missing value is shown as «Нет данных»."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from gift_sniper.config import Settings
from gift_sniper.domain.enums import MonochromeStatus, PurchaseStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.types import Enrichment, ListingSnapshot, Share
from gift_sniper.services.percentages import NO_DATA, format_model_share, format_percent, format_permille

MONO_LABEL = {
    MonochromeStatus.MONOCHROME: "Да",
    MonochromeStatus.NOT_MONOCHROME: "Нет",
    MonochromeStatus.UNKNOWN: "Неизвестно",
}


def e(value: object | None) -> str:
    return escape(str(value)) if value not in (None, "") else NO_DATA


def listing_url(settings: Settings, listing: ListingSnapshot) -> str:
    """Link to the listing. Only documented URL forms are used (see docs/DATA_SOURCES.md)."""
    if settings.mrkt_listing_url_template:
        try:
            return settings.mrkt_listing_url_template.format(
                gift_id=listing.gift_id, slug=listing.telegram_slug or "", number=listing.number or ""
            )
        except (KeyError, IndexError, ValueError):
            pass
    return settings.mrkt_app_url


def telegram_nft_url(listing: ListingSnapshot) -> str | None:
    slug = listing.telegram_slug
    return f"https://t.me/nft/{slug}" if slug else None


def rarity_line(listing: ListingSnapshot) -> str:
    values = [
        ("модель", listing.model_rarity_permille),
        ("фон", listing.backdrop_rarity_permille),
        ("символ", listing.symbol_rarity_permille),
    ]
    if all(v is None for _, v in values):
        return NO_DATA
    return " · ".join(f"{label} {format_permille(v)}" for label, v in values) + " (по данным MRKT)"


def data_age_text(hours: float | None) -> str:
    if hours is None:
        return "данных Gift Wiki нет"
    if hours < 1:
        return "обновлено менее часа назад"
    return f"обновлено {hours:.0f} ч назад" + (" ⚠️ устарели" if hours > 24 else "")


def share_text(share: Share | None) -> str:
    return format_model_share(share)


def new_listing_text(
    listing: ListingSnapshot,
    enrichment: Enrichment,
    *,
    status_line: str,
    price_note: str = "",
) -> str:
    v = enrichment.verdict
    lines = [
        "🎁 <b>Новый подарок на MRKT</b>" if not price_note else "📉 <b>Снижение цены на MRKT</b>",
        f"Подарок: {e(listing.title)}",
        f"Коллекция: {e(listing.collection_title or listing.collection_name)}",
        f"Модель: {e(listing.model_name)}",
        f"Фон: {e(listing.backdrop_name)}",
        f"Символ: {e(listing.symbol_name)}",
        f"Цена: {format_ton(listing.price_nano)}" + (f" ({escape(price_note)})" if price_note else ""),
        f"Редкость: {rarity_line(listing)}",
        f"Монохром: {MONO_LABEL[v.status]}" + (f" ({v.gw_type.value})" if v.gw_type else ""),
        f"Доля монохромных моделей: {share_text(enrichment.model_share)}",
        f"Вероятность выпадения модели: {format_percent(enrichment.model_drop_probability)}",
        f"Источник классификации: Gift Wiki ({data_age_text(enrichment.giftwiki_data_age_hours)})",
        f"Статус: {escape(status_line)}",
    ]
    return "\n".join(lines)


def monochrome_text(listing: ListingSnapshot, enrichment: Enrichment, *, filter_names: list[str]) -> str:
    v = enrichment.verdict
    lines = [
        "⚫ <b>Найден подтверждённый монохром</b>",
        f"Подарок: {e(listing.title)}",
        f"Коллекция: {e(listing.collection_title or listing.collection_name)}",
        f"Модель: {e(listing.model_name)}",
        f"Фон: {e(listing.backdrop_name)}",
        f"Тип по Gift Wiki: {e(v.gw_type.value if v.gw_type else None)}",
        f"Цена: {format_ton(listing.price_nano)}",
        f"Доля монохромных моделей: {share_text(enrichment.model_share)}",
        f"Вероятность выпадения модели: {format_percent(enrichment.model_drop_probability)}",
        f"Источник: Gift Wiki ({data_age_text(enrichment.giftwiki_data_age_hours)})",
    ]
    if filter_names:
        lines.append("Фильтры: " + escape(", ".join(filter_names)))
    return "\n".join(lines)


def details_text(
    listing: ListingSnapshot, enrichment: Enrichment, *, monochrome_listing_share: str | None
) -> str:
    v = enrichment.verdict
    discount = NO_DATA
    if enrichment.discount_percent is not None and enrichment.discount_reference_nano is not None:
        discount = (
            f"{format_percent(enrichment.discount_percent)} к медиане {format_ton(enrichment.discount_reference_nano)} "
            f"({enrichment.discount_samples} наблюдений той же коллекции и модели)"
        )
    elif enrichment.discount_samples:
        discount = f"Нет данных (наблюдений: {enrichment.discount_samples}, нужно больше)"
    lines = [
        f"🔎 <b>{e(listing.title)}</b>",
        f"ID MRKT: <code>{escape(listing.gift_id)}</code>",
        f"Коллекция: {e(listing.collection_title or listing.collection_name)}",
        f"Модель: {e(listing.model_name)} — {format_permille(listing.model_rarity_permille)}",
        f"Фон: {e(listing.backdrop_name)} — {format_permille(listing.backdrop_rarity_permille)}",
        f"Символ: {e(listing.symbol_name)} — {format_permille(listing.symbol_rarity_permille)}",
        f"Цена: {format_ton(listing.price_nano)}",
        "",
        f"<b>Монохром:</b> {MONO_LABEL[v.status]} (<code>{v.status.value}</code>)",
        f"Обоснование: {escape(v.reason)}",
        f"Тип Gift Wiki: {e(v.gw_type.value if v.gw_type else None)}",
        f"Запись Gift Wiki: {e(v.record_id)}",
        f"Сверка цветов фона: {escape(v.color_check)}",
        f"Данные Gift Wiki: {data_age_text(enrichment.giftwiki_data_age_hours)}",
        "",
        f"A. Доля монохромных моделей (Gift Wiki): {share_text(enrichment.model_share)}",
        f"B. Вероятность выпадения модели (Gift Wiki): {format_percent(enrichment.model_drop_probability)}",
        f"C. Доля монохромных листингов (MRKT): {monochrome_listing_share or NO_DATA}",
        "",
        f"Скидка: {discount}",
        "Доля моделей не является вероятностью получить монохром.",
    ]
    if v.photo_url:
        lines.append(f'<a href="{escape(v.photo_url, quote=True)}">Фото (Gift Wiki)</a>')
    return "\n".join(lines)


OPERATION_STATUS = {
    PurchaseStatus.FAILED: "не выполнена",
    PurchaseStatus.CANCELLED: "не выполнена",
    PurchaseStatus.UNKNOWN: "неизвестен, ожидает проверки",
    PurchaseStatus.SUBMITTED: "ожидает проверки",
    PurchaseStatus.RESERVED: "ожидает проверки",
}


def purchase_confirmed_text(
    *,
    title: str,
    collection: str | None,
    model: str | None,
    price_nano: int | None,
    filter_name: str | None,
    remaining: str,
) -> str:
    return "\n".join(
        [
            "✅ <b>Покупка подтверждена</b>",
            f"Подарок: {e(title)}",
            f"Коллекция: {e(collection)}",
            f"Модель: {e(model)}",
            f"Цена: {format_ton(price_nano)}",
            f"Фильтр: {e(filter_name or 'ручная покупка')}",
            f"Остаток бюджета: {escape(remaining)}",
        ]
    )


def purchase_failed_text(*, title: str, reason: str, status: PurchaseStatus) -> str:
    return "\n".join(
        [
            "⚠️ <b>Покупка не подтверждена</b>",
            f"Подарок: {e(title)}",
            f"Причина: {escape(reason)}",
            f"Статус операции: {OPERATION_STATUS.get(status, 'неизвестен')}",
        ]
    )


def dry_run_text(
    *, title: str, collection: str | None, model: str | None, price_nano: int | None, filter_name: str | None
) -> str:
    return "\n".join(
        [
            "🧪 <b>Тестовый режим: подарок был бы куплен</b>",
            f"Подарок: {e(title)}",
            f"Коллекция: {e(collection)}",
            f"Модель: {e(model)}",
            f"Цена: {format_ton(price_nano)}",
            f"Фильтр: {e(filter_name or 'ручная покупка')}",
            "Реальная покупка не выполнялась.",
        ]
    )


def utc_label(moment: datetime | None) -> str:
    if moment is None:
        return NO_DATA
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
