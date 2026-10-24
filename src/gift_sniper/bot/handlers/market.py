"""🔎 search, 🆕 new listings, listing details, manual purchase, 📊/📈 statistics, 📜 history."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import FilterCb, HistoryCb, Menu, StatsCb
from gift_sniper.bot.ui import back_kb, show
from gift_sniper.config import RunMode
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.domain.enums import FilterKind, MonochromeStatus, PurchaseMode, PurchaseStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.integrations.mrkt.parsing import parse_gift
from gift_sniper.services import texts
from gift_sniper.services.container import Services
from gift_sniper.services.filters import describe_criteria
from gift_sniper.services.percentages import (
    format_listing_share,
    format_model_share,
    format_permille,
    monochrome_listing_share,
)
from gift_sniper.services.purchase import PurchaseRequest

router = Router(name="market")

MONO_ICON = {"MONOCHROME": "⚫", "NOT_MONOCHROME": "⚪", "UNKNOWN": "❔"}
STATUS_ICON = {
    PurchaseStatus.CONFIRMED.value: "✅",
    PurchaseStatus.FAILED.value: "❌",
    PurchaseStatus.UNKNOWN.value: "❓",
    PurchaseStatus.DRY_RUN.value: "🧪",
    PurchaseStatus.CANCELLED.value: "🚫",
    PurchaseStatus.RESERVED.value: "⏳",
    PurchaseStatus.SUBMITTED.value: "⏳",
}


# ------------------------------------------------------------------ search
@router.callback_query(Menu.filter(F.section == "search"))
async def cb_search_menu(callback: CallbackQuery, services: Services) -> None:
    async with services.sessionmaker() as session:
        rows = await filters_repo.list_filters(session, callback.from_user.id)
    b = InlineKeyboardBuilder()
    for row in rows:
        icon = "⚫" if row.kind == FilterKind.MONOCHROME.value else "🎁"
        b.button(text=f"{icon} {row.name}", callback_data=FilterCb(action="search", id=row.id))
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(1)
    text = "🔎 <b>Поиск по фильтрам</b>\nВыберите фильтр: бот запросит текущие листинги MRKT и проверит их локально."
    if not rows:
        text += "\n\nСначала создайте фильтр в ⚙️ Настройки фильтров."
    await show(callback, text, b.as_markup())


@router.callback_query(FilterCb.filter(F.action == "search"))
async def cb_search(callback: CallbackQuery, callback_data: FilterCb, services: Services) -> None:
    async with services.sessionmaker() as session:
        row = await filters_repo.get_filter(session, callback.from_user.id, callback_data.id)
    if row is None:
        await callback.answer("Фильтр не найден", show_alert=True)
        return
    if not services.mrkt.configured:
        await show(callback, "MRKT не подключён: задайте MRKT_ACCESS_TOKEN или MRKT_INIT_DATA.", back_kb())
        return
    await callback.answer("Ищу на MRKT…")
    spec = filters_repo.to_spec(row)
    try:
        result = await services.search.search(spec)
    except MrktError as exc:
        await show(callback, f"⚠️ MRKT недоступен: {escape(str(exc))}", back_kb("search", "« Поиск"))
        return
    lines = [
        f"🔎 <b>Поиск: «{escape(spec.name)}»</b>",
        "Критерии: " + escape("; ".join(describe_criteria(spec.kind, spec.criteria))),
        f"Просмотрено объявлений MRKT: {result.scanned}"
        + ("" if result.exhausted else " (есть ещё страницы)")
        + f", подходит: {result.matched}",
        "Доля монохромных листингов: "
        + format_listing_share(
            result.share, computed_at=result.computed_at, scope="подходящие объявления выборки"
        ),
    ]
    if spec.criteria.only_new_listings:
        lines.append("ℹ️ Условие «только новые» в поиске не применяется (ищутся текущие объявления).")
    b = InlineKeyboardBuilder()
    if not result.items:
        lines.append("\nПодходящих объявлений не найдено.")
    for index, (listing, enrichment) in enumerate(result.items, start=1):
        v = enrichment.verdict
        lines.append(
            f"{index}. {texts.gift_link(listing)} — {format_ton(listing.price_nano)} — "
            f"{escape(listing.model_name or 'модель ?')} ({format_permille(listing.model_rarity_permille)}) — "
            f"{MONO_ICON[v.status.value]} {texts.MONO_LABEL[v.status]}"
            + (f" ({v.gw_type.value})" if v.gw_type else "")
        )
        token = await services.notifier.make_token(
            {"gift_id": listing.gift_id, "price": listing.price_nano, "raw": listing.raw}
        )
        b.button(text=f"🔎 {index}", callback_data=f"ld:{token}")
    b.adjust(5)
    b.row(
        InlineKeyboardButton(text="🔄 Повторить", callback_data=FilterCb(action="search", id=spec.id).pack()),
        InlineKeyboardButton(text="« Фильтр", callback_data=FilterCb(action="view", id=spec.id).pack()),
    )
    b.row(InlineKeyboardButton(text="« Меню", callback_data=Menu(section="main").pack()))
    await show(callback, "\n".join(lines), b.as_markup())


# ------------------------------------------------------------------ new listings
@router.callback_query(Menu.filter(F.section == "new"))
async def cb_new_listings(callback: CallbackQuery, services: Services) -> None:
    async with services.sessionmaker() as session:
        rows = await listings_repo.recent_listings(session, limit=10)
    lines = ["🆕 <b>Новые листинги</b> (последние 10 по данным мониторинга MRKT)"]
    b = InlineKeyboardBuilder()
    if not rows:
        lines.append("\nПока ничего не обнаружено. Проверьте, что MRKT подключён и мониторинг работает.")
    for index, (listing, gift) in enumerate(rows, start=1):
        title = (gift.collection_title or gift.collection_name or "Подарок") + (
            f" #{gift.number}" if gift.number is not None else ""
        )
        status = {"active": "в продаже", "sold": "продан", "removed": "снят"}.get(
            listing.status, listing.status
        )
        lines.append(
            f"{index}. {listing.first_seen_at:%H:%M:%S} {texts.linked_title(title, texts.nft_url(gift.name))} — "
            f"{format_ton(listing.price_nano)} — "
            f"{MONO_ICON.get(listing.monochrome_status, '❔')} — {status}"
        )
        token = await services.notifier.make_token(
            {"gift_id": gift.id, "price": listing.price_nano, "raw": gift.raw}
        )
        b.button(text=f"🔎 {index}", callback_data=f"ld:{token}")
    b.adjust(5)
    b.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=Menu(section="new").pack()),
        InlineKeyboardButton(text="« Меню", callback_data=Menu(section="main").pack()),
    )
    await show(callback, "\n".join(lines), b.as_markup())


# ------------------------------------------------------------------ listing details & manual purchase
@router.callback_query(F.data.startswith("ld:"))
async def cb_details(callback: CallbackQuery, services: Services) -> None:
    token = (callback.data or "")[3:]
    payload = await services.notifier.read_token(token)
    listing = parse_gift(payload.get("raw")) if payload else None
    if listing is None:
        await callback.answer("Данные устарели, откройте листинг заново", show_alert=True)
        return
    if payload and payload.get("price") is not None:
        listing = replace(listing, price_nano=int(payload["price"]))
    enrichment = await services.enricher.enrich(listing)
    share_c = None
    if listing.collection_name:
        since = datetime.now(UTC) - timedelta(hours=24)
        async with services.sessionmaker() as session:
            statuses = await listings_repo.collection_statuses(session, listing.collection_name, since)
        if statuses:
            share_c = format_listing_share(
                monochrome_listing_share(statuses),
                computed_at=datetime.now(UTC),
                scope="активные объявления коллекции за 24 ч, наблюдения бота",
            )
    text = texts.details_text(listing, enrichment, monochrome_listing_share=share_c)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть MRKT", url=texts.listing_url(services.settings, listing))],
            [InlineKeyboardButton(text="Купить вручную", callback_data=f"mb:{token}")],
            [InlineKeyboardButton(text="« Меню", callback_data=Menu(section="main").pack())],
        ]
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("mb:"))
async def cb_manual_buy(callback: CallbackQuery, services: Services, can_purchase: bool) -> None:
    token = (callback.data or "")[3:]
    payload = await services.notifier.read_token(token)
    listing = parse_gift(payload.get("raw")) if payload else None
    if listing is None or payload is None:
        await callback.answer("Данные устарели, откройте листинг заново", show_alert=True)
        return
    run_mode = await services.control.run_mode()
    url = texts.listing_url(services.settings, listing)
    if not can_purchase or run_mode is RunMode.NOTIFY_ONLY:
        reason = "у вас нет права покупок" if not can_purchase else "бот работает в режиме только уведомлений"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть MRKT", url=url)]])
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(
                f"Покупка через бота недоступна: {reason}. Купите вручную в MRKT.", reply_markup=kb
            )
        return
    price = payload.get("price")
    mode_note = (
        "🧪 Тестовый режим: реальной покупки не будет."
        if run_mode is RunMode.DRY_RUN
        else ("💸 Будет выполнена реальная покупка.")
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Купить за {format_ton(price)}", callback_data=f"mbok:{token}")],
            [InlineKeyboardButton(text="Отмена", callback_data=Menu(section="main").pack())],
        ]
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Купить <b>{texts.gift_link(listing)}</b> за {format_ton(price)}?\n{mode_note}\n"
            "Перед покупкой бот перепроверит наличие, цену (не выше указанной) и ваши лимиты.",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("mbok:"))
async def cb_manual_buy_confirm(callback: CallbackQuery, services: Services, can_purchase: bool) -> None:
    token = (callback.data or "")[5:]
    payload = await services.notifier.read_token(token)
    if payload is None or not can_purchase or payload.get("price") is None:
        await callback.answer("Покупка недоступна или данные устарели", show_alert=True)
        return
    await services.redis.delete(f"{services.settings.redis_prefix}:btn:{token}")  # one confirmation per token
    await show(callback, "⏳ Проверяю объявление и лимиты…")
    request = PurchaseRequest(
        user_id=callback.from_user.id,
        gift_id=str(payload["gift_id"]),
        expected_price_nano=int(payload["price"]),
        mode=PurchaseMode.MANUAL,
        trigger="manual",
        detected_at=datetime.now(UTC),
    )
    result = await services.purchase.execute(request)
    if result.status is None:
        await show(callback, f"🚫 Покупка не выполнена: {escape(result.reason)}", back_kb())
    else:
        await show(callback, "Запрос обработан, результат отправлен отдельным сообщением.", back_kb())


# ------------------------------------------------------------------ statistics
@router.callback_query(Menu.filter(F.section == "mstats"))
async def cb_market_stats(callback: CallbackQuery, services: Services) -> None:
    await _market_stats(callback, services, 24)


@router.callback_query(StatsCb.filter(F.scope == "market"))
async def cb_market_stats_period(callback: CallbackQuery, callback_data: StatsCb, services: Services) -> None:
    await _market_stats(callback, services, callback_data.hours)


async def _market_stats(callback: CallbackQuery, services: Services, hours: int) -> None:
    stats = await services.stats.market(user_id=callback.from_user.id, period_hours=hours)
    period = f"{texts.utc_label(stats.period_start)} — {texts.utc_label(stats.period_end)}"
    lines = [
        f"📊 <b>Статистика рынка</b> ({'сутки' if hours == 24 else f'{hours // 24} дн.'})",
        f"Период: {period}",
        "Источник: наблюдения мониторинга MRKT ботом (не полная история рынка)",
        "",
        f"Новых листингов: {stats.new_listings}",
        f"Подходящих под ваши фильтры: {stats.matching_listings}",
        f"Средняя цена: {format_ton(stats.avg_price_nano)} · медиана: {format_ton(stats.median_price_nano)}",
        f"Подтверждённых монохромов (Gift Wiki): {stats.monochrome_listings}",
        "Доля монохромных листингов (все новые листинги периода): "
        + format_listing_share(stats.listing_share),
    ]
    if stats.cheapest:
        lines.append("\n<b>Самые дешёвые активные предложения</b> (статус мог измениться):")
        for title, _collection, model, price, mono in stats.cheapest:
            lines.append(
                f"• {escape(title)} — {escape(model or '?')} — {format_ton(price)} {MONO_ICON.get(mono, '')}"
            )
    if stats.collection_shares:
        lines.append("\n<b>Доля монохромных моделей</b> (Gift Wiki, по известным моделям):")
        for name, share in stats.collection_shares:
            lines.append(f"• {escape(name)}: {format_model_share(share)}")
    if stats.daily_medians:
        lines.append("\n<b>Медиана цены новых листингов по дням</b> (UTC):")
        for day, median, count in stats.daily_medians:
            lines.append(f"• {day}: {format_ton(median)} ({count} шт.)")
    lines += [
        "",
        "<b>Ваши покупки за период</b>",
        f"Попыток: {stats.attempts} · подтверждено: {stats.confirmed} · потрачено: {format_ton(stats.spent_nano)}",
        f"Ошибок и неизвестных: {stats.errors} · отменено: {stats.cancelled} · тестовых: {stats.dry_run}",
        "",
        "Выгодность не определяется по редкости: скидка считается только к медиане сопоставимых цен.",
    ]
    b = InlineKeyboardBuilder()
    b.button(text="24 ч", callback_data=StatsCb(scope="market", hours=24))
    b.button(text="7 дней", callback_data=StatsCb(scope="market", hours=24 * 7))
    b.button(text="30 дней", callback_data=StatsCb(scope="market", hours=24 * 30))
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(3, 1)
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(Menu.filter(F.section == "ustats"))
async def cb_user_stats(callback: CallbackQuery, services: Services) -> None:
    stats = await services.stats.user(user_id=callback.from_user.id, period_days=30)
    lines = [
        "📈 <b>Моя статистика</b> (30 дней)",
        f"Период: {texts.utc_label(stats.period_start)} — {texts.utc_label(stats.period_end)}",
        "",
        f"Попыток покупки: {stats.attempts}",
        f"Подтверждённых покупок: {stats.confirmed} на {format_ton(stats.spent_nano)}",
        f"Не выполнено: {stats.failed} · результат неизвестен: {stats.unknown} · отменено: {stats.cancelled}",
        f"Тестовый режим: было бы куплено {stats.dry_run} на {format_ton(stats.dry_run_nano)}",
        "",
        "<b>По фильтрам</b>:" if stats.filters else "Фильтров нет.",
    ]
    for row in stats.filters:
        icon = "⚫" if row.kind == FilterKind.MONOCHROME.value else "🎁"
        lines.append(
            f"{icon} {escape(row.name)} {'✅' if row.enabled else '⏸'}: срабатываний {row.hits}, "
            f"попыток {row.attempts}, куплено {row.confirmed} на {format_ton(row.spent_nano)}"
        )
    await show(callback, "\n".join(lines), back_kb())


# ------------------------------------------------------------------ history
@router.callback_query(Menu.filter(F.section == "history"))
async def cb_history(callback: CallbackQuery, services: Services) -> None:
    await _history(callback, services, 0)


@router.callback_query(HistoryCb.filter())
async def cb_history_page(callback: CallbackQuery, callback_data: HistoryCb, services: Services) -> None:
    await _history(callback, services, max(0, callback_data.page))


async def _history(callback: CallbackQuery, services: Services, page: int) -> None:
    per_page = 10
    async with services.sessionmaker() as session:
        attempts = await purchases_repo.list_attempts(
            session, callback.from_user.id, limit=per_page + 1, offset=page * per_page
        )
    has_next = len(attempts) > per_page
    attempts = attempts[:per_page]
    lines = [
        f"📜 <b>История операций</b> (стр. {page + 1})",
        "✅ подтверждена · ❌ не выполнена · ❓ неизвестно · 🧪 тест · 🚫 отменена",
    ]
    if not attempts:
        lines.append("\nОпераций пока нет.")
    for a in attempts:
        title = (a.collection_name or a.gift_id) + (f" #{a.number}" if a.number is not None else "")
        price = a.final_price_nano if a.final_price_nano is not None else a.expected_price_nano
        mono = (
            f" ⚫{a.monochrome_type or ''}"
            if a.monochrome_status == MonochromeStatus.MONOCHROME.value
            else ""
        )
        lines.append(
            f"{STATUS_ICON.get(a.status, '•')} {a.created_at:%m-%d %H:%M} {escape(title)} — {format_ton(price)}{mono}"
            f" — {escape(a.filter_name or a.mode)}"
        )
        if a.reason and a.status != PurchaseStatus.CONFIRMED.value:
            lines.append(f"   └ {escape(a.reason[:160])}")
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="◀", callback_data=HistoryCb(page=page - 1))
    if has_next:
        b.button(text="▶", callback_data=HistoryCb(page=page + 1))
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(2, 1)
    await show(callback, "\n".join(lines), b.as_markup())
