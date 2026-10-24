"""`python -m gift_sniper check`: verifies data sources and integrations against the live services.

It checks only what can be verified without spending money. The purchase endpoint
(POST /gifts/buy) cannot be verified without a real purchase, and the report says so explicitly.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from gift_sniper.config import Settings
from gift_sniper.domain.normalize import color_candidates, normalize_name
from gift_sniper.webapp.images import absolute_url, collection_thumb, gift_image, giftname

OK, WARN, FAIL = "✅", "⚠️", "❌"


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = False

    def add(self, status: str, text: str) -> None:
        if status == FAIL:
            self.failed = True
        self.lines.append(f"{status} {text}")

    def print(self) -> None:
        print("\n".join(self.lines))


EXPECTED_GIFT_FIELDS = [
    "id",
    "collectionName",
    "modelName",
    "backdropName",
    "symbolName",
    "salePrice",
    "isOnSale",
]
EXPECTED_GW_FIELDS = ["_id", "gift_id", "gift_name", "model_name", "backdrop_name", "type"]


async def _check_storage(settings: Settings, report: Report) -> None:
    from redis.asyncio import Redis
    from sqlalchemy import text

    from gift_sniper.db.session import create_engine

    engine = create_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
        report.add(
            OK if version else WARN, f"PostgreSQL доступен, версия миграций: {version or 'не применены'}"
        )
    except Exception as exc:
        report.add(FAIL, f"PostgreSQL недоступен: {exc}")
    finally:
        await engine.dispose()
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
        report.add(OK, "Redis доступен")
    except Exception as exc:
        report.add(FAIL, f"Redis недоступен: {exc}")
    finally:
        await redis.aclose()


async def _check_telegram(settings: Settings, report: Report) -> None:
    if not settings.telegram_bot_token:
        report.add(FAIL, "TELEGRAM_BOT_TOKEN не задан")
        return
    from aiogram import Bot

    bot = Bot(settings.telegram_bot_token.get_secret_value())
    try:
        me = await bot.get_me()
        report.add(OK, f"Telegram бот: @{me.username}")
    except Exception as exc:
        report.add(FAIL, f"Telegram бот недоступен: {exc}")
    finally:
        await bot.session.close()
    if not settings.admin_user_ids:
        report.add(WARN, "ADMIN_USER_IDS пуст — управлять ботом будет некому")


async def _check_mrkt(settings: Settings, report: Report, samples: list[tuple[str, str]]) -> list[str]:
    from gift_sniper.integrations.mrkt import MrktClient, MrktError, SalingQuery

    collections: list[str] = []
    if not settings.mrkt_configured:
        report.add(
            FAIL,
            "MRKT не настроен: выполните `python -m gift_sniper mrkt-login` (нужны TELEGRAM_API_ID и "
            "TELEGRAM_API_HASH) или задайте MRKT_ACCESS_TOKEN",
        )
        return collections
    sources = [
        name
        for name, enabled in (
            ("MRKT_ACCESS_TOKEN", bool(settings.mrkt_access_token)),
            ("MRKT_INIT_DATA", bool(settings.mrkt_init_data)),
            ("Telegram-сессия (автообновление токена)", settings.mrkt_session_available),
        )
        if enabled
    ]
    report.add(OK, "Авторизация MRKT: " + ", ".join(sources))
    client = MrktClient(settings)
    await client.start()
    try:
        try:
            listings, _ = await client.search_listings(SalingQuery(count=5))
            if not listings:
                report.add(WARN, "MRKT gifts/saling: ответ без листингов")
            else:
                raw: dict[str, Any] = listings[0].raw
                missing = [f for f in EXPECTED_GIFT_FIELDS if f not in raw]
                report.add(
                    OK if not missing else WARN,
                    f"MRKT gifts/saling: {len(listings)} листингов"
                    + (f", нет полей: {missing}" if missing else ""),
                )
                gift = await client.get_gift(listings[0].gift_id)
                report.add(
                    OK if gift else WARN,
                    "MRKT gifts/gift/{id}: " + ("работает" if gift else "не вернул подарок"),
                )
                first = listings[0]
                thumb = collection_thumb(giftname(first.collection_name, slug=first.name))
                if thumb:
                    samples.append(
                        (
                            f"обложки коллекции Fragment ({first.collection_title or first.collection_name})",
                            thumb,
                        )
                    )
                picture = gift_image(first.name)
                if picture:
                    samples.append((f"подарка Fragment ({first.name})", picture))
                colors = sum(1 for item in listings if item.backdrop_center_color is not None)
                report.add(
                    OK if colors else WARN, f"Цвета фона в листингах MRKT: {colors} из {len(listings)}"
                )
        except MrktError as exc:
            report.add(FAIL, str(exc))
        try:
            events, _ = await client.feed(count=20)
            kinds = ", ".join(f"{kind}: {n}" for kind, n in Counter(e.type for e in events).most_common())
            report.add(
                OK if events else WARN, f"MRKT feed: {len(events)} событий" + (f" ({kinds})" if kinds else "")
            )
        except MrktError as exc:
            report.add(FAIL, f"{exc} (мониторинг можно переключить на MRKT_MONITOR_SOURCE=saling)")
        try:
            balance = await client.balance_nano()
            report.add(
                OK if balance is not None else WARN,
                "MRKT balance: " + ("получен" if balance is not None else "нет поля hard"),
            )
        except MrktError as exc:
            report.add(WARN, str(exc))
        try:
            collections = [c.name for c in await client.collections()]
            report.add(OK if collections else WARN, f"MRKT gifts/collections: {len(collections)} коллекций")
        except MrktError as exc:
            collections = []
            report.add(WARN, str(exc))
        for kind, label in (("model", "моделей"), ("backdrop", "фонов")):
            if not collections:
                break
            try:
                items = await client.collection_attributes(kind, collections[0])
                rarity = sum(1 for i in items if i.rarity_permille is not None)
                report.add(
                    OK if items else WARN,
                    f"MRKT gifts/{kind}s ({collections[0]}): {len(items)} {label}, с редкостью {rarity}"
                    + ("" if items else " — мини-приложение покажет только замеченные ботом"),
                )
            except MrktError as exc:
                report.add(WARN, f"{exc} (мини-приложение покажет только замеченные ботом {label})")
        report.add(
            WARN,
            "MRKT gifts/buy нельзя проверить без реальной покупки. Начните с RUN_MODE=dry_run, затем выполните "
            "одну ручную покупку недорогого подарка и проверьте результат в «История операций».",
        )
    finally:
        await client.close()
    return collections


async def _check_giftwiki(
    settings: Settings, report: Report, mrkt_collections: list[str], samples: list[tuple[str, str]]
) -> None:
    from gift_sniper.domain.enums import GiftWikiMonochromeType
    from gift_sniper.integrations.giftwiki import GiftWikiClient, GiftWikiError

    if not settings.giftwiki_configured:
        report.add(
            FAIL, "GIFTWIKI_API_KEY не задан: классификация монохромов невозможна (статус всегда UNKNOWN)"
        )
        return
    from gift_sniper.envfile import mask
    from gift_sniper.integrations.giftwiki import key_looks_truncated

    assert settings.giftwiki_api_key is not None
    key = settings.giftwiki_api_key.get_secret_value()
    if key_looks_truncated(key):
        report.add(FAIL, f"GIFTWIKI_API_KEY={key}: это только начало ключа — вставьте в .env ключ целиком")
        return
    report.add(OK, f"GIFTWIKI_API_KEY: {mask(key)} ({len(key)} символов)")
    client = GiftWikiClient(settings)
    await client.start()
    try:
        records = await client.list_monochromes(1)
        if not records:
            report.add(WARN, "Gift Wiki /gifts/monochromes?page=1: пустой список")
            return
        missing = sorted({f for r in records for f in EXPECTED_GW_FIELDS if f not in r.raw})
        report.add(
            OK if not missing else WARN,
            f"Gift Wiki /gifts/monochromes: {len(records)} записей на стр. 1"
            + (f", нет полей: {missing}" if missing else ""),
        )
        types = {r.type_raw for r in records}
        undocumented = sorted(t for t in types if GiftWikiMonochromeType.parse(t) is None and t)
        report.add(
            OK if not undocumented else WARN,
            f"Типы монохромов: {sorted(t for t in types if t)}"
            + (f" — недокументированные: {undocumented}" if undocumented else ""),
        )
        extra = sorted(
            {k for r in records for k in r.raw}
            - set(EXPECTED_GW_FIELDS)
            - {"center_color", "edge_color", "pattern_color", "text_color", "photo_url", "animation_url"}
        )
        if extra:
            report.add(OK, f"Дополнительные поля записей (сохраняются в raw, не интерпретируются): {extra}")
        photo = next((r for r in records if r.photo_url), None)
        url = absolute_url(photo.photo_url, settings.giftwiki_api_base_url) if photo else None
        report.add(
            OK if url else WARN,
            f"Фото пар в Gift Wiki: у {sum(1 for r in records if r.photo_url)} из {len(records)} записей",
        )
        if photo and url:
            samples.append(
                (f"Gift Wiki ({photo.gift_name} · {photo.model_name} · {photo.backdrop_name})", url)
            )
        parsable = sum(1 for r in records if color_candidates(r.center_color))
        report.add(
            OK if parsable else WARN,
            f"Формат цветов Gift Wiki распознан у {parsable} из {len(records)} записей",
        )
        name = next((r.gift_name for r in records if r.gift_name), None)
        if name:
            try:
                full = await client.monochromes_for_gift(gift_name=name)
                report.add(
                    OK, f"Gift Wiki поиск gift_name={name!r}: {len(full)} записей (полный список подарка)"
                )
            except GiftWikiError as exc:
                report.add(
                    WARN,
                    f"Gift Wiki поиск по gift_name недоступен: {exc} (полнота будет только по пагинации)",
                )
        if mrkt_collections:
            gw_names = {normalize_name(r.gift_name) for r in records if r.gift_name}
            matched = [c for c in mrkt_collections if normalize_name(c) in gw_names]
            report.add(
                OK, f"Совпадение названий MRKT ↔ Gift Wiki на первой странице: {len(matched)} коллекций"
            )
    except GiftWikiError as exc:
        report.add(FAIL, f"Gift Wiki: {exc}")
    finally:
        await client.close()


async def _check_images(report: Report, samples: list[tuple[str, str]]) -> None:
    """The Mini App shows these pictures straight from their sites: check that they really are pictures."""
    import aiohttp

    if not samples:
        report.add(WARN, "Картинки мини-приложения: нет примеров для проверки")
        return
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=True) as http:
        for label, url in samples:
            try:
                async with http.get(url) as resp:
                    kind = resp.headers.get("Content-Type", "")
                    await resp.content.read(512)
                ok = resp.status == 200 and kind.startswith("image/")
                report.add(
                    OK if ok else WARN, f"Картинка {label}: HTTP {resp.status} {kind or 'без типа'} — {url}"
                )
            except (aiohttp.ClientError, TimeoutError) as exc:
                report.add(WARN, f"Картинка {label}: {type(exc).__name__} — {url}")


async def run_selfcheck(settings: Settings) -> int:
    report = Report()
    report.add(OK, f"RUN_MODE={settings.run_mode.value}")
    await _check_storage(settings, report)
    await _check_telegram(settings, report)
    samples: list[tuple[str, str]] = []
    collections = await _check_mrkt(settings, report, samples)
    await _check_giftwiki(settings, report, collections, samples)
    await _check_images(report, samples)
    report.print()
    return 1 if report.failed else 0
