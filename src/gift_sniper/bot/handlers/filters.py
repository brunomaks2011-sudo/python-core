"""⚙️ Filter management: list, create, edit every field, copy, enable/disable, delete."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import FilterCb, Menu, NotifyCb
from gift_sniper.bot.parsing import (
    InputError,
    parse_int,
    parse_name,
    parse_names,
    parse_percent,
    parse_period,
    parse_permille_range,
    parse_ton,
    parse_ton_range,
)
from gift_sniper.bot.states import Input
from gift_sniper.bot.ui import show
from gift_sniper.db.models import Filter
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.domain.enums import FilterKind, GiftWikiMonochromeType
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.services.container import Services
from gift_sniper.services.filters import FilterCriteria, FilterLimits, describe_criteria, describe_limits

router = Router(name="filters")


@dataclass(frozen=True)
class FieldDef:
    label: str
    parser: str  # ton_range | names | permille_range | percent | int | ton | period | name
    target: str  # criteria | limits | name
    attrs: tuple[str, ...]
    prompt: str
    mono_only: bool = False


FIELDS: dict[str, FieldDef] = {
    "name": FieldDef("Название", "name", "name", (), "Введите новое название фильтра (до 64 символов)."),
    "price": FieldDef(
        "Цена",
        "ton_range",
        "criteria",
        ("min_price_nano", "max_price_nano"),
        "Диапазон цены в TON: «1.5-10», «-10» (только верхняя граница), «2-» (только нижняя) или «-» (сбросить).",
    ),
    "col": FieldDef(
        "Коллекции",
        "names",
        "criteria",
        ("collections",),
        "Названия коллекций через запятую (как на MRKT), «-» — любые.",
    ),
    "mod": FieldDef(
        "Модели", "names", "criteria", ("models",), "Названия моделей через запятую, «-» — любые."
    ),
    "bkd": FieldDef(
        "Фоны", "names", "criteria", ("backdrops",), "Названия фонов через запятую, «-» — любые."
    ),
    "sym": FieldDef(
        "Символы", "names", "criteria", ("symbols",), "Названия символов через запятую, «-» — любые."
    ),
    "xcol": FieldDef(
        "Исключить коллекции",
        "names",
        "criteria",
        ("exclude_collections",),
        "Коллекции, которые нужно исключить, через запятую. «-» — сбросить.",
    ),
    "xmod": FieldDef(
        "Исключить модели",
        "names",
        "criteria",
        ("exclude_models",),
        "Модели, которые нужно исключить, через запятую. «-» — сбросить.",
    ),
    "mrar": FieldDef(
        "Редкость модели",
        "permille_range",
        "criteria",
        ("model_rarity_min_permille", "model_rarity_max_permille"),
        "Редкость модели в промилле (‰, по данным MRKT; 10‰ = 1%). Меньше — реже. Формат «от-до», "
        "например «-15» (не чаще 1.5%), «-» — сбросить.",
    ),
    "brar": FieldDef(
        "Редкость фона",
        "permille_range",
        "criteria",
        ("backdrop_rarity_min_permille", "backdrop_rarity_max_permille"),
        "Редкость фона в ‰ (по данным MRKT), формат «от-до», «-» — сбросить.",
    ),
    "srar": FieldDef(
        "Редкость символа",
        "permille_range",
        "criteria",
        ("symbol_rarity_min_permille", "symbol_rarity_max_permille"),
        "Редкость символа в ‰ (по данным MRKT), формат «от-до», «-» — сбросить.",
    ),
    "disc": FieldDef(
        "Мин. скидка",
        "percent",
        "criteria",
        ("min_discount_percent",),
        "Минимальная скидка в % к медиане цен той же коллекции и модели за последние дни "
        "(нужно не меньше 5 наблюдений, иначе листинг не проходит). «-» — без условия.",
    ),
    "mshare": FieldDef(
        "Мин. доля монохромных моделей",
        "percent",
        "criteria",
        ("min_monochrome_model_share_percent",),
        "Минимальная доля монохромных моделей коллекции, % (по известным моделям). «-» — без условия.",
        mono_only=True,
    ),
    "cnt": FieldDef(
        "Сколько купить",
        "int",
        "limits",
        ("max_count",),
        "Сколько подарков максимум купить этим фильтром. «-» — без ограничения.",
    ),
    "ppg": FieldDef(
        "Макс. цена подарка",
        "ton",
        "limits",
        ("max_price_per_gift_nano",),
        "Максимальная цена одного подарка в TON. «-» — сбросить.",
    ),
    "pop": FieldDef(
        "Макс. сумма операции",
        "ton",
        "limits",
        ("max_per_operation_nano",),
        "Максимальная сумма одной операции покупки в TON. «-» — сбросить.",
    ),
    "day": FieldDef(
        "Бюджет на день",
        "ton",
        "limits",
        ("daily_limit_nano",),
        "Бюджет фильтра на день в TON. «-» — без ограничения.",
    ),
    "tot": FieldDef(
        "Бюджет всего",
        "ton",
        "limits",
        ("total_limit_nano",),
        "Общий бюджет фильтра в TON. «-» — без ограничения.",
    ),
    "per": FieldDef(
        "Покупок за период",
        "period",
        "limits",
        ("period_max_count", "period_hours"),
        "Максимум покупок за период: «количество/часы», например «3/24». «-» — сбросить.",
    ),
}

PARSERS: dict[str, Any] = {
    "ton_range": parse_ton_range,
    "names": parse_names,
    "permille_range": parse_permille_range,
    "percent": parse_percent,
    "int": lambda t: parse_int(t, minimum=1),
    "ton": parse_ton,
    "period": parse_period,
    "name": parse_name,
}

KIND_ICON = {FilterKind.REGULAR.value: "🎁", FilterKind.MONOCHROME.value: "⚫"}


async def _invalidate(services: Services) -> None:
    await services.filter_cache.invalidate()


def filters_list_kb(rows: list[Filter], *, kind: FilterKind | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        state = "✅" if row.enabled else "⏸"
        auto = " 🤖" if row.autobuy else ""
        builder.button(
            text=f"{state} {KIND_ICON.get(row.kind, '')} {row.name}{auto}",
            callback_data=FilterCb(action="view", id=row.id),
        )
    if kind in (None, FilterKind.REGULAR):
        builder.button(text="➕ Фильтр подарков", callback_data=FilterCb(action="new", field="regular"))
    if kind in (None, FilterKind.MONOCHROME):
        builder.button(text="➕ Фильтр монохромов", callback_data=FilterCb(action="new", field="monochrome"))
    if kind is None:
        builder.button(text="🔔 Уведомления", callback_data=NotifyCb(action="view"))
    builder.button(text="« Меню", callback_data=Menu(section="main"))
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(Menu.filter(F.section == "filters"))
async def cb_filters(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    async with services.sessionmaker() as session:
        rows = await filters_repo.list_filters(session, callback.from_user.id)
    text = (
        "⚙️ <b>Настройки фильтров</b>\n"
        "✅ — включён, ⏸ — выключен, 🤖 — автопокупка по фильтру.\n"
        "🎁 — обычная автопокупка, ⚫ — автопокупка монохромов (покупает только статус MONOCHROME по Gift Wiki)."
    )
    if not rows:
        text += "\n\nФильтров пока нет."
    await show(callback, text, filters_list_kb(rows, kind=None))


async def render_filter(services: Services, row: Filter) -> tuple[str, InlineKeyboardMarkup]:
    spec = filters_repo.to_spec(row)
    async with services.sessionmaker() as session:
        stats = await filters_repo.filter_stats(session, row.id)
    kind = spec.kind
    title = "⚫ Фильтр монохромов" if kind is FilterKind.MONOCHROME else "🎁 Фильтр подарков"
    lines = [
        f"{title} «{escape(spec.name)}»",
        f"Статус: {'✅ включён' if spec.enabled else '⏸ выключен'}",
        f"Автопокупка по фильтру: {'✅ да' if spec.autobuy else '❌ нет'}",
        "",
        "<b>Критерии</b>",
        *[f"• {escape(line)}" for line in describe_criteria(kind, spec.criteria)],
        "",
        "<b>Лимиты фильтра</b>",
        *[f"• {escape(line)}" for line in describe_limits(spec.limits)],
        "",
        "<b>Статистика</b>",
        f"Срабатываний: {stats['hits']} · попыток покупки: {stats['attempts']}",
        f"Куплено: {stats['confirmed']} на {format_ton(stats['spent_nano'])} · в тестовом режиме: {stats['dry_run']}",
    ]
    b = InlineKeyboardBuilder()
    b.button(
        text="⏸ Выключить" if spec.enabled else "✅ Включить",
        callback_data=FilterCb(action="toggle", id=row.id),
    )
    b.button(
        text="🤖 Автопокупка: вкл" if spec.autobuy else "🤖 Автопокупка: выкл",
        callback_data=FilterCb(action="autobuy", id=row.id),
    )
    for key, field in FIELDS.items():
        if field.mono_only and kind is not FilterKind.MONOCHROME:
            continue
        if key == "name":
            continue
        b.button(text=f"✏️ {field.label}", callback_data=FilterCb(action="edit", id=row.id, field=key))
    b.button(
        text=f"🆕 Только новые: {'да' if spec.criteria.only_new_listings else 'нет'}",
        callback_data=FilterCb(action="onlynew", id=row.id),
    )
    if kind is FilterKind.MONOCHROME:
        selected = set(spec.criteria.monochrome_types)
        for t in GiftWikiMonochromeType:
            mark = "☑️" if (not selected or t.value in selected) else "⬜"
            b.button(
                text=f"{mark} {t.value}", callback_data=FilterCb(action="mtype", id=row.id, field=t.value)
            )
    b.button(text="✏️ Название", callback_data=FilterCb(action="edit", id=row.id, field="name"))
    b.button(text="📋 Копировать", callback_data=FilterCb(action="copy", id=row.id))
    b.button(text="🔎 Найти сейчас", callback_data=FilterCb(action="search", id=row.id))
    b.button(text="🗑 Удалить", callback_data=FilterCb(action="delete", id=row.id))
    b.button(text="« Фильтры", callback_data=Menu(section="filters"))
    b.adjust(2)
    if kind is FilterKind.MONOCHROME:
        lines.append("")
        lines.append("Типы Gift Wiki: ☑️ — разрешён (если ничего не выбрано, разрешены все).")
    return "\n".join(lines), b.as_markup()


async def _load(services: Services, user_id: int, filter_id: int) -> Filter | None:
    async with services.sessionmaker() as session:
        return await filters_repo.get_filter(session, user_id, filter_id)


@router.callback_query(FilterCb.filter(F.action == "view"))
async def cb_view(
    callback: CallbackQuery, callback_data: FilterCb, services: Services, state: FSMContext
) -> None:
    await state.clear()
    row = await _load(services, callback.from_user.id, callback_data.id)
    if row is None:
        await callback.answer("Фильтр не найден", show_alert=True)
        return
    text, kb = await render_filter(services, row)
    await show(callback, text, kb)


@router.callback_query(FilterCb.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, callback_data: FilterCb, state: FSMContext) -> None:
    kind = FilterKind.MONOCHROME if callback_data.field == "monochrome" else FilterKind.REGULAR
    await state.set_state(Input.filter_name)
    await state.update_data(kind=kind.value)
    await show(
        callback,
        f"Введите название нового {'фильтра монохромов' if kind is FilterKind.MONOCHROME else 'фильтра подарков'} "
        "(до 64 символов). /cancel — отмена.",
    )


@router.message(Input.filter_name)
async def msg_new_name(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        name = parse_name(message.text or "")
    except InputError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    kind = FilterKind(data.get("kind", FilterKind.REGULAR.value))
    try:
        async with services.sessionmaker() as session, session.begin():
            row = await filters_repo.create_filter(session, message.from_user.id, name, kind)  # type: ignore[union-attr]
            await misc.audit(
                session, "filter_created", user_id=row.user_id, filter_id=row.id, kind=kind.value
            )
    except ValueError as exc:
        await state.clear()
        await message.answer(f"⚠️ {exc}")
        return
    await state.clear()
    await _invalidate(services)
    text, kb = await render_filter(services, row)
    await message.answer(
        "Фильтр создан выключенным. Настройте критерии и включите его.\n\n" + text, reply_markup=kb
    )


async def _mutate(callback: CallbackQuery, services: Services, filter_id: int, action: str) -> None:
    async with services.sessionmaker() as session, session.begin():
        row = await filters_repo.get_filter(session, callback.from_user.id, filter_id)
        if row is None:
            await callback.answer("Фильтр не найден", show_alert=True)
            return
        if action == "toggle":
            filters_repo.set_enabled(row, not row.enabled)
        elif action == "autobuy":
            row.autobuy = not row.autobuy
        elif action == "onlynew":
            criteria = FilterCriteria.model_validate(row.criteria or {})
            criteria.only_new_listings = not criteria.only_new_listings
            filters_repo.update_criteria(row, criteria)
        await misc.audit(session, f"filter_{action}", user_id=row.user_id, filter_id=row.id)
    await _invalidate(services)
    row = await _load(services, callback.from_user.id, filter_id)
    assert row is not None
    text, kb = await render_filter(services, row)
    await show(callback, text, kb)


@router.callback_query(FilterCb.filter(F.action.in_({"toggle", "autobuy", "onlynew"})))
async def cb_toggle(callback: CallbackQuery, callback_data: FilterCb, services: Services) -> None:
    await _mutate(callback, services, callback_data.id, callback_data.action)


@router.callback_query(FilterCb.filter(F.action == "mtype"))
async def cb_mtype(callback: CallbackQuery, callback_data: FilterCb, services: Services) -> None:
    async with services.sessionmaker() as session, session.begin():
        row = await filters_repo.get_filter(session, callback.from_user.id, callback_data.id)
        if row is None:
            await callback.answer("Фильтр не найден", show_alert=True)
            return
        criteria = FilterCriteria.model_validate(row.criteria or {})
        selected = set(criteria.monochrome_types) or {t.value for t in GiftWikiMonochromeType}
        selected ^= {callback_data.field}
        if not selected:
            await callback.answer("Должен остаться хотя бы один тип", show_alert=True)
            return
        all_types = {t.value for t in GiftWikiMonochromeType}
        criteria.monochrome_types = [] if selected == all_types else sorted(selected)
        filters_repo.update_criteria(row, criteria)
    await _invalidate(services)
    row = await _load(services, callback.from_user.id, callback_data.id)
    assert row is not None
    text, kb = await render_filter(services, row)
    await show(callback, text, kb)


@router.callback_query(FilterCb.filter(F.action == "copy"))
async def cb_copy(callback: CallbackQuery, callback_data: FilterCb, services: Services) -> None:
    try:
        async with services.sessionmaker() as session, session.begin():
            row = await filters_repo.get_filter(session, callback.from_user.id, callback_data.id)
            if row is None:
                await callback.answer("Фильтр не найден", show_alert=True)
                return
            copy = await filters_repo.copy_filter(session, row)
            await misc.audit(session, "filter_copied", user_id=row.user_id, source=row.id, filter_id=copy.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    text, kb = await render_filter(services, copy)
    await show(callback, "📋 Копия создана (выключена).\n\n" + text, kb)


@router.callback_query(FilterCb.filter(F.action == "delete"))
async def cb_delete(callback: CallbackQuery, callback_data: FilterCb) -> None:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Да, удалить", callback_data=FilterCb(action="delete_ok", id=callback_data.id))
    b.button(text="Отмена", callback_data=FilterCb(action="view", id=callback_data.id))
    b.adjust(2)
    await show(callback, "Удалить фильтр? История покупок сохранится.", b.as_markup())


@router.callback_query(FilterCb.filter(F.action == "delete_ok"))
async def cb_delete_ok(callback: CallbackQuery, callback_data: FilterCb, services: Services) -> None:
    async with services.sessionmaker() as session, session.begin():
        row = await filters_repo.get_filter(session, callback.from_user.id, callback_data.id)
        if row is not None:
            await filters_repo.delete_filter(session, row)
            await misc.audit(session, "filter_deleted", user_id=row.user_id, filter_id=row.id)
    await _invalidate(services)
    async with services.sessionmaker() as session:
        rows = await filters_repo.list_filters(session, callback.from_user.id)
    await show(callback, "🗑 Фильтр удалён.", filters_list_kb(rows, kind=None))


@router.callback_query(FilterCb.filter(F.action == "edit"))
async def cb_edit(callback: CallbackQuery, callback_data: FilterCb, state: FSMContext) -> None:
    field = FIELDS.get(callback_data.field)
    if field is None:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await state.set_state(Input.filter_field)
    await state.update_data(filter_id=callback_data.id, field=callback_data.field)
    await show(callback, f"✏️ <b>{field.label}</b>\n{escape(field.prompt)}\n\n/cancel — отмена.")


async def _unknown_collections(services: Services, names: list[str]) -> list[str]:
    async with services.sessionmaker() as session:
        known = set(await listings_repo.known_collection_names(session))
        known |= {g.gift_name for g in await giftwiki_repo.gifts_overview(session) if g.gift_name}
    if not known:
        return []
    known_norm = {normalize_name(k) for k in known}
    return [n for n in names if normalize_name(n) not in known_norm]


@router.message(Input.filter_field)
async def msg_edit_field(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    field = FIELDS.get(str(data.get("field")))
    filter_id = int(data.get("filter_id", 0))
    if field is None:
        await state.clear()
        return
    try:
        value = PARSERS[field.parser](message.text or "")
    except InputError as exc:
        await message.answer(f"⚠️ {exc}\nПопробуйте ещё раз или /cancel.")
        return
    warning = ""
    async with services.sessionmaker() as session, session.begin():
        row = await filters_repo.get_filter(session, message.from_user.id, filter_id)  # type: ignore[union-attr]
        if row is None:
            await state.clear()
            await message.answer("Фильтр не найден.")
            return
        if field.target == "name":
            row.name = value
        else:
            model_cls = FilterCriteria if field.target == "criteria" else FilterLimits
            current = model_cls.model_validate(
                (row.criteria if field.target == "criteria" else row.limits) or {}
            )
            values = value if isinstance(value, tuple) else (value,)
            for attr, item in zip(field.attrs, values, strict=True):
                setattr(current, attr, item)
            if field.target == "criteria":
                filters_repo.update_criteria(row, current)  # type: ignore[arg-type]
            else:
                filters_repo.update_limits(row, current)  # type: ignore[arg-type]
        await misc.audit(session, "filter_edited", user_id=row.user_id, filter_id=row.id, field=field.label)
    if field.parser == "names" and field.attrs[0] in ("collections", "exclude_collections") and value:
        unknown = await _unknown_collections(services, value)
        if unknown:
            warning = (
                "\n⚠️ Не найдены среди известных коллекций MRKT/Gift Wiki: "
                + escape(", ".join(unknown))
                + ". Проверьте написание."
            )
    await state.clear()
    await _invalidate(services)
    row = await _load(services, message.from_user.id, filter_id)  # type: ignore[union-attr]
    assert row is not None
    text, kb = await render_filter(services, row)
    await message.answer(f"Сохранено.{warning}\n\n{text}", reply_markup=kb)
