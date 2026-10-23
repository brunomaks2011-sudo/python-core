"""📚 Gift Wiki: sync status, gifts with monochrome records, gift card, manual sync (admins)."""

from __future__ import annotations

import asyncio
from collections import Counter
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import Menu, WikiCb
from gift_sniper.bot.ui import show
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.domain.enums import GiftWikiMonochromeType
from gift_sniper.services import texts
from gift_sniper.services.container import Services
from gift_sniper.services.percentages import format_model_share, monochrome_model_share

router = Router(name="wiki")
PER_PAGE = 10
_sync_tasks: set[asyncio.Task[object]] = set()


@router.callback_query(Menu.filter(F.section == "wiki"))
async def cb_wiki(callback: CallbackQuery, services: Services, is_admin: bool) -> None:
    async with services.sessionmaker() as session:
        runs = await giftwiki_repo.last_runs(session, limit=3)
        success = await giftwiki_repo.last_success(session)
        gifts, records = await giftwiki_repo.counts(session)
        mapping = await giftwiki_repo.mapping_counts(session)
    age = services.store.snapshot.age_hours()
    lines = [
        "📚 <b>Gift Wiki</b>",
        "Источник классификации монохромов: api.giftwiki.tg, GET /gifts/monochromes.",
        f"Подарков с данными: {gifts} · монохромных записей: {records}",
        f"Последняя успешная синхронизация: {texts.utc_label(success.finished_at if success else None)}"
        + ("" if age is None else f" ({texts.data_age_text(age)})"),
    ]
    if mapping:
        lines.append(
            "Сопоставление коллекций MRKT: "
            f"найдено {mapping.get('matched', 0)}, вручную {mapping.get('manual', 0)}, "
            f"неоднозначно {mapping.get('ambiguous', 0)}, нет в Gift Wiki {mapping.get('not_found', 0)}"
            + (" (исправить: /map)" if is_admin and mapping.get("ambiguous") else "")
        )
    if not services.settings.giftwiki_configured:
        lines.append("⚠️ GIFTWIKI_API_KEY не задан — синхронизация невозможна.")
    if runs:
        lines.append("\n<b>Последние запуски</b>:")
        for run in runs:
            lines.append(
                f"• {texts.utc_label(run.started_at)} — {run.status}: страниц {run.pages_fetched}, "
                f"записей {run.records_fetched}, добавлено {run.records_added}, удалено {run.records_removed}"
                + (f"\n  ошибка: {escape(run.error[:200])}" if run.error else "")
            )
    lines += [
        "",
        "Gift Wiki классифицирует пары «модель + фон» по уровням high, medium, low, combo. "
        "Полный список моделей, вероятности выпадения и описания в доступном API не опубликованы.",
        f"Канал Gift Wiki: {escape(services.settings.giftwiki_public_url)}",
    ]
    b = InlineKeyboardBuilder()
    b.button(text="📋 Подарки с монохромами", callback_data=WikiCb(action="list", page=0))
    if is_admin:
        b.button(text="🔄 Синхронизировать сейчас", callback_data=WikiCb(action="sync"))
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(1)
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(WikiCb.filter(F.action == "list"))
async def cb_list(callback: CallbackQuery, callback_data: WikiCb, services: Services) -> None:
    async with services.sessionmaker() as session:
        gifts = [g for g in await giftwiki_repo.gifts_overview(session) if g.records_count > 0]
    page = max(0, callback_data.page)
    chunk = gifts[page * PER_PAGE : (page + 1) * PER_PAGE]
    lines = [f"📋 <b>Подарки с монохромными записями</b> ({len(gifts)}), стр. {page + 1}"]
    b = InlineKeyboardBuilder()
    for gift in chunk:
        name = gift.gift_name or gift.gift_id
        lines.append(
            f"• {escape(name)} — записей: {gift.records_count}"
            + ("" if gift.coverage_complete else " (неполно)")
        )
        token = await services.notifier.make_token({"gw_gift": gift.gift_id})
        b.button(text=name[:40], callback_data=WikiCb(action="gift", token=token))
    b.adjust(2)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=WikiCb(action="list", page=page - 1).pack()))
    if (page + 1) * PER_PAGE < len(gifts):
        nav.append(InlineKeyboardButton(text="▶", callback_data=WikiCb(action="list", page=page + 1).pack()))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="« Gift Wiki", callback_data=Menu(section="wiki").pack()))
    if not gifts:
        lines.append("\nДанных пока нет: дождитесь синхронизации.")
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(WikiCb.filter(F.action == "gift"))
async def cb_gift(callback: CallbackQuery, callback_data: WikiCb, services: Services) -> None:
    payload = await services.notifier.read_token(callback_data.token)
    gift_id = payload.get("gw_gift") if payload else None
    if not gift_id:
        await callback.answer("Данные устарели", show_alert=True)
        return
    async with services.sessionmaker() as session:
        gift = await giftwiki_repo.get_gift(session, str(gift_id))
        records = await giftwiki_repo.records_of_gift(session, str(gift_id))
        observed = await listings_repo.observed_models(
            session, [gift.gift_name] if gift and gift.gift_name else []
        )
    if gift is None:
        await callback.answer("Подарок не найден", show_alert=True)
        return
    by_type = Counter(r.type for r in records)
    mono_models = {r.model_norm: r.model_name for r in records if GiftWikiMonochromeType.parse(r.type)}
    share = monochrome_model_share(mono_models.keys(), observed.keys(), rarity_by_model=observed)
    lines = [
        f"📚 <b>{escape(gift.gift_name or gift.gift_id)}</b>",
        f"Gift Wiki gift_id: <code>{escape(gift.gift_id)}</code>",
        f"Данные: {texts.utc_label(gift.last_synced_at)}, полный список: {'да' if gift.coverage_complete else 'нет'}"
        + (f" ({gift.coverage_source})" if gift.coverage_source else ""),
        "Записей по типам: "
        + (
            ", ".join(f"{t}: {by_type[t]}" for t in ["high", "medium", "low", "combo"] if by_type.get(t))
            or "нет"
        ),
        f"Монохромных моделей (хотя бы с одним фоном): {len(mono_models)}",
        f"Доля монохромных моделей: {format_model_share(share)}",
        "Вероятность выпадения модели: Нет данных (не опубликована в доступном API Gift Wiki)",
        "",
        "<b>Пары модель + фон</b>:",
    ]
    for rec in records[:40]:
        lines.append(
            f"• {escape(rec.model_name or '?')} + {escape(rec.backdrop_name or '?')} — {escape(rec.type or '?')}"
        )
    if len(records) > 40:
        lines.append(f"… и ещё {len(records) - 40}")
    photo = next((r.photo_url for r in records if r.photo_url), None)
    if photo:
        lines.append(f'\n<a href="{escape(photo, quote=True)}">Пример изображения (Gift Wiki)</a>')
    b = InlineKeyboardBuilder()
    b.button(text="« Список", callback_data=WikiCb(action="list", page=0))
    b.button(text="« Gift Wiki", callback_data=Menu(section="wiki"))
    b.adjust(2)
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(WikiCb.filter(F.action == "sync"))
async def cb_sync(callback: CallbackQuery, services: Services, is_admin: bool) -> None:
    if not is_admin:
        await callback.answer("Только для администраторов", show_alert=True)
        return
    await callback.answer("Синхронизация запущена")

    async def run() -> None:
        report = await services.sync.run(trigger="manual")
        await services.notifier.send(
            callback.from_user.id,
            f"📚 Синхронизация Gift Wiki: {report.status}. Записей: {report.records}, добавлено: {report.added}, "
            f"удалено: {report.removed}." + (f"\nОшибка: {escape(report.error)}" if report.error else ""),
            kind="admin",
            critical=True,
        )

    task = asyncio.create_task(run())
    _sync_tasks.add(task)
    task.add_done_callback(_sync_tasks.discard)


@router.message(Command("map"))
async def cmd_map(message: Message, command: CommandObject, services: Services, is_admin: bool) -> None:
    """Manual MRKT -> Gift Wiki mapping for ambiguous or differently named collections (admins only).

    /map                              — list ambiguous / not found collections
    /map <MRKT коллекция> = <gift_id или название в Gift Wiki>
    /map <MRKT коллекция> = -         — remove the manual mapping
    """
    if not is_admin:
        await message.answer("Команда доступна администраторам.")
        return
    args = (command.args or "").strip()
    if not args:
        async with services.sessionmaker() as session:
            rows = [
                m
                for m in await giftwiki_repo.list_mappings(session)
                if m.status in ("ambiguous", "not_found")
            ]
        lines = [
            "Коллекции без однозначного соответствия:" if rows else "Все известные коллекции сопоставлены."
        ]
        for m in rows[:50]:
            candidates = ", ".join(m.candidates) if m.candidates else "—"
            lines.append(f"• {escape(m.mrkt_collection_name)} — {m.status} (кандидаты: {escape(candidates)})")
        lines.append("\nФормат: /map Коллекция MRKT = gift_id или название в Gift Wiki")
        await message.answer("\n".join(lines))
        return
    if "=" not in args:
        await message.answer("Формат: /map Коллекция MRKT = gift_id или название в Gift Wiki (или «-»)")
        return
    left, right = (part.strip() for part in args.split("=", 1))
    snapshot = services.store.snapshot
    user_id = message.from_user.id if message.from_user else None
    if right in ("-", ""):
        async with services.sessionmaker() as session, session.begin():
            await giftwiki_repo.delete_mapping(session, left)
            await misc.audit(session, "mapping_removed", user_id=user_id, collection=left)
        await services.store.bump()
        await message.answer(f"Ручное сопоставление для «{escape(left)}» удалено.")
        return
    gift_id = right if right in snapshot.gifts else None
    if gift_id is None:
        match = snapshot.match_collection(right)
        if match.status != "matched" or match.gift_id is None:
            await message.answer(
                f"Подарок «{escape(right)}» не найден в данных Gift Wiki однозначно ({match.status})."
            )
            return
        gift_id = match.gift_id
    async with services.sessionmaker() as session, session.begin():
        await giftwiki_repo.save_mapping(
            session,
            left,
            gift_id=gift_id,
            status="manual",
            method="manual",
            candidates=[gift_id],
            verified_by=user_id,
        )
        await misc.audit(session, "mapping_set", user_id=user_id, collection=left, gift_id=gift_id)
    await services.store.bump()
    name = snapshot.gifts[gift_id].gift_name if gift_id in snapshot.gifts else gift_id
    await message.answer(
        f"✅ «{escape(left)}» → Gift Wiki «{escape(name or gift_id)}» (<code>{escape(gift_id)}</code>)."
    )
