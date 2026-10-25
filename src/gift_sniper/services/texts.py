"""Message templates (HTML parse mode). Every missing value is shown as «Нет данных»."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from gift_sniper.config import Settings
from gift_sniper.domain.enums import MonochromeStatus, PurchaseStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.types import Enrichment, ListingSnapshot, Share, nft_slug
from gift_sniper.services.percentages import NO_DATA, format_model_share, format_percent, format_permille

MONO_LABEL = {
    MonochromeStatus.MONOCHROME: "Да",
    MonochromeStatus.NOT_MONOCHROME: "Нет",
    MonochromeStatus.UNKNOWN: "Неизвестно",
}


def e(value: object | None) -> str:
    return escape(str(value)) if value not in (None, "") else NO_DATA


def listing_url(settings: Settings, listing: ListingSnapshot) -> str | None:
    """Link that opens this gift in MRKT, from MRKT_LISTING_URL_TEMPLATE (by default the format of MRKT's
    "Поделиться" button). A template that cannot be filled gives no link rather than the market's main page.
    """
    if not settings.mrkt_listing_url_template:
        return None
    try:
        return settings.mrkt_listing_url_template.format(
            gift_id=listing.gift_id,
            gift_id_hex=listing.gift_id.replace("-", "").lower(),
            slug=listing.telegram_slug or "",
            number=listing.number or "",
        )
    except (KeyError, IndexError, ValueError):
        return None


def nft_url(name: str | None) -> str | None:
    slug = nft_slug(name)
    return f"https://t.me/nft/{slug}" if slug else None


def telegram_nft_url(listing: ListingSnapshot) -> str | None:
    return nft_url(listing.name)


def linked_title(title: str, url: str | None) -> str:
    """Gift title (collection + number) as a link to the gift in Telegram when its slug is known."""
    return f'<a href="{escape(url, quote=True)}">{escape(title)}</a>' if url else escape(title)


def gift_link(listing: ListingSnapshot) -> str:
    return linked_title(listing.title, telegram_nft_url(listing))


def data_age_text(hours: float | None) -> str:
    if hours is None:
        return "ещё не загружены"
    if hours < 1:
        return "обновлено менее часа назад"
    return f"обновлено {hours:.0f} ч назад" + (" ⚠️ устарели" if hours > 24 else "")


def share_text(share: Share | None) -> str:
    return format_model_share(share)


def _attributes(listing: ListingSnapshot) -> str:
    """'January 0.6% · Electric Purple 1.2% · Star 0.5%' (rarity only where MRKT gives it)."""
    parts = []
    for name, permille in (
        (listing.model_name, listing.model_rarity_permille),
        (listing.backdrop_name, listing.backdrop_rarity_permille),
        (listing.symbol_name, listing.symbol_rarity_permille),
    ):
        if name:
            parts.append(escape(name) + (f" {format_permille(permille)}" if permille is not None else ""))
    return " · ".join(parts)


def _monochrome_lines(enrichment: Enrichment, *, status: bool = True) -> list[str]:
    v = enrichment.verdict
    lines = []
    if status and v.status is MonochromeStatus.MONOCHROME:
        lines.append("⚫ Монохром" + (f" · {escape(v.gw_type.value)}" if v.gw_type else ""))
    share = enrichment.model_share
    if share is not None and share.percent is not None:
        lines.append(
            f"Монохромных моделей: {share.numerator} из {share.denominator} — {format_percent(share.percent)}"
        )
    if enrichment.model_drop_probability is not None:
        lines.append(f"Шанс модели: {format_percent(enrichment.model_drop_probability)}")
    return lines


def new_listing_text(
    listing: ListingSnapshot,
    enrichment: Enrichment,
    *,
    status_line: str,
    price_note: str = "",
) -> str:
    lines = [
        f"📉 <b>Цена снижена</b> · {escape(price_note)}" if price_note else "🎁 <b>Новый листинг</b>",
        f"<b>{gift_link(listing)}</b>",
        _attributes(listing),
        f"💰 <b>{format_ton(listing.price_nano)}</b>",
        *_monochrome_lines(enrichment),
    ]
    if status_line:
        lines.append(f"<i>{escape(status_line[:1].upper() + status_line[1:])}</i>")
    return "\n".join(line for line in lines if line)


def monochrome_text(listing: ListingSnapshot, enrichment: Enrichment, *, filter_names: list[str]) -> str:
    v = enrichment.verdict
    lines = [
        "⚫ <b>Монохром</b>" + (f" · {escape(v.gw_type.value)}" if v.gw_type else ""),
        f"<b>{gift_link(listing)}</b>",
        _attributes(listing),
        f"💰 <b>{format_ton(listing.price_nano)}</b>",
        *_monochrome_lines(enrichment, status=False),
    ]
    if filter_names:
        lines.append("<i>Правило: " + escape(", ".join(filter_names)) + "</i>")
    return "\n".join(line for line in lines if line)


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
        f"🔎 <b>{gift_link(listing)}</b>",
        f"ID MRKT: <code>{escape(listing.gift_id)}</code>",
        f"Коллекция: {e(listing.collection_title or listing.collection_name)}",
        f"Модель: {e(listing.model_name)} — {format_permille(listing.model_rarity_permille)}",
        f"Фон: {e(listing.backdrop_name)} — {format_permille(listing.backdrop_rarity_permille)}",
        f"Символ: {e(listing.symbol_name)} — {format_permille(listing.symbol_rarity_permille)}",
        f"Цена: {format_ton(listing.price_nano)}",
        "",
        f"<b>Монохром:</b> {MONO_LABEL[v.status]} (<code>{v.status.value}</code>)",
        f"Обоснование: {escape(v.reason)}",
        f"Тип монохрома: {e(v.gw_type.value if v.gw_type else None)}",
        f"Сверка цветов фона: {escape(v.color_check)}",
        f"Данные о монохромах: {data_age_text(enrichment.giftwiki_data_age_hours)}",
        "",
        f"A. Доля монохромных моделей: {share_text(enrichment.model_share)}",
        f"B. Вероятность выпадения модели: {format_percent(enrichment.model_drop_probability)}",
        f"C. Доля монохромных листингов: {monochrome_listing_share or NO_DATA}",
        "",
        f"Скидка: {discount}",
        "Доля моделей не является вероятностью получить монохром.",
    ]
    if v.photo_url:
        lines.append(f'<a href="{escape(v.photo_url, quote=True)}">Фото монохрома</a>')
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
    url: str | None = None,
    collection: str | None,
    model: str | None,
    price_nano: int | None,
    filter_name: str | None,
    remaining: str,
) -> str:
    return "\n".join(
        [
            "✅ <b>Покупка подтверждена</b>",
            f"Подарок: {linked_title(title, url)}",
            f"Коллекция: {e(collection)}",
            f"Модель: {e(model)}",
            f"Цена: {format_ton(price_nano)}",
            f"Фильтр: {e(filter_name or 'ручная покупка')}",
            f"Остаток бюджета: {escape(remaining)}",
        ]
    )


def purchase_failed_text(*, title: str, reason: str, status: PurchaseStatus, url: str | None = None) -> str:
    return "\n".join(
        [
            "⚠️ <b>Покупка не подтверждена</b>",
            f"Подарок: {linked_title(title, url)}",
            f"Причина: {escape(reason)}",
            f"Статус операции: {OPERATION_STATUS.get(status, 'неизвестен')}",
        ]
    )


def dry_run_text(
    *,
    title: str,
    collection: str | None,
    model: str | None,
    price_nano: int | None,
    filter_name: str | None,
    url: str | None = None,
) -> str:
    return "\n".join(
        [
            "🧪 <b>Тестовый режим: подарок был бы куплен</b>",
            f"Подарок: {linked_title(title, url)}",
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
