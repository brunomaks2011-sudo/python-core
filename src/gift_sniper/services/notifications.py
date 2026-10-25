"""Notification delivery: preferences, dedup (DB), per-user rate limits (Redis), Telegram flood control."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from typing import Any, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.db.repo import misc, users
from gift_sniper.domain.enums import FilterKind, MonochromeStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import Enrichment, ListingSnapshot
from gift_sniper.integrations.http import AsyncRateLimiter
from gift_sniper.metrics import NOTIFICATIONS
from gift_sniper.services import texts
from gift_sniper.services.filter_cache import UserFlags
from gift_sniper.services.filters import FilterSpec
from gift_sniper.services.user_prefs import NotificationSettings

log = logging.getLogger(__name__)


class MessageSender(Protocol):
    async def send(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup | None = None,
        *,
        preview_url: str | None = None,
    ) -> bool: ...


class TelegramSender:
    """Sends through aiogram with a global rate limit and Telegram RetryAfter handling."""

    def __init__(self, bot: Any, messages_per_second: float) -> None:
        self.bot = bot
        self.limiter = AsyncRateLimiter(messages_per_second, burst=max(1, int(messages_per_second)))
        self.blocked: set[int] = set()

    async def send(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup | None = None,
        *,
        preview_url: str | None = None,
    ) -> bool:
        from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

        # previews stay off except the one explicitly requested (a gift's t.me/nft card)
        preview = LinkPreviewOptions(url=preview_url) if preview_url else LinkPreviewOptions(is_disabled=True)
        for _ in range(3):
            await self.limiter.acquire()
            try:
                await self.bot.send_message(
                    chat_id, text, reply_markup=keyboard, link_preview_options=preview
                )
                return True
            except TelegramRetryAfter as exc:
                self.limiter.pause(float(exc.retry_after))
                await asyncio.sleep(float(exc.retry_after))
            except TelegramForbiddenError:
                self.blocked.add(chat_id)
                return False
            except TelegramBadRequest:
                log.exception("telegram rejected a message", extra={"chat_id": chat_id})
                return False
        return False


class Notifier:
    def __init__(
        self,
        settings: Settings,
        sender: MessageSender,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
    ) -> None:
        self.settings = settings
        self.sender = sender
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.prefix = settings.redis_prefix

    # ------------------------------------------------------------------ tokens for buttons
    async def make_token(self, payload: dict[str, Any], ttl: int = 6 * 3600) -> str:
        token = secrets.token_urlsafe(6)
        await self.redis.set(f"{self.prefix}:btn:{token}", json.dumps(payload, default=str), ex=ttl)
        return token

    async def read_token(self, token: str) -> dict[str, Any] | None:
        raw = await self.redis.get(f"{self.prefix}:btn:{token}")
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None

    # ------------------------------------------------------------------ core send
    async def _rate_ok(self, user_id: int, limit: int) -> tuple[bool, bool]:
        """Returns (allowed, first_overflow)."""
        window = int(time.time() // 60)
        key = f"{self.prefix}:rl:{user_id}:{window}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 120)
        if count <= limit:
            return True, False
        return False, count == limit + 1

    async def send(
        self,
        user_id: int,
        text: str,
        *,
        kind: str,
        keyboard: InlineKeyboardMarkup | None = None,
        dedup_key: str | None = None,
        listing_id: int | None = None,
        critical: bool = False,
        max_per_minute: int | None = None,
        preview_url: str | None = None,
    ) -> bool:
        """Deliver a message. Never raises: a notification problem must not stop monitoring or buying."""
        try:
            return await self._send(
                user_id,
                text,
                kind=kind,
                keyboard=keyboard,
                dedup_key=dedup_key,
                listing_id=listing_id,
                critical=critical,
                max_per_minute=max_per_minute,
                preview_url=preview_url,
            )
        except Exception:
            log.exception("notification failed", extra={"user_id": user_id, "kind": kind})
            NOTIFICATIONS.labels(kind, "error").inc()
            return False

    async def _send(
        self,
        user_id: int,
        text: str,
        *,
        kind: str,
        keyboard: InlineKeyboardMarkup | None,
        dedup_key: str | None,
        listing_id: int | None,
        critical: bool,
        max_per_minute: int | None,
        preview_url: str | None = None,
    ) -> bool:
        if dedup_key:
            async with self.sessionmaker() as session, session.begin():
                claimed = await misc.claim_notification(
                    session, user_id=user_id, kind=kind, dedup_key=dedup_key, listing_id=listing_id
                )
            if not claimed:
                NOTIFICATIONS.labels(kind, "duplicate").inc()
                return False
        if not critical:
            allowed, first_overflow = await self._rate_ok(
                user_id, max_per_minute or self.settings.notify_default_max_per_minute
            )
            if not allowed:
                NOTIFICATIONS.labels(kind, "rate_limited").inc()
                if dedup_key:
                    async with self.sessionmaker() as session, session.begin():
                        await misc.set_notification_status(
                            session, user_id=user_id, dedup_key=dedup_key, status="suppressed"
                        )
                if first_overflow:
                    await self.sender.send(
                        user_id,
                        "⏳ Достигнут лимит уведомлений в минуту. Остальные уведомления за эту минуту пропущены "
                        "(покупки и ошибки приходят всегда). Лимит меняется в ⚙️ Настройки → 🔔 Уведомления.",
                    )
                return False
        ok = await self.sender.send(user_id, text, keyboard, preview_url=preview_url)
        NOTIFICATIONS.labels(kind, "sent" if ok else "failed").inc()
        if not ok:
            if dedup_key:
                async with self.sessionmaker() as session, session.begin():
                    await misc.set_notification_status(
                        session, user_id=user_id, dedup_key=dedup_key, status="failed"
                    )
            if isinstance(self.sender, TelegramSender) and user_id in self.sender.blocked:
                async with self.sessionmaker() as session, session.begin():
                    await users.mark_blocked(session, user_id)
        return ok

    async def admins(self, text: str, *, dedup_key: str | None = None) -> None:
        for admin_id in self.settings.admin_user_ids:
            await self.send(admin_id, text, kind="admin", dedup_key=dedup_key, critical=True)

    # ------------------------------------------------------------------ listing notifications
    def _in_scope(
        self, prefs: NotificationSettings, listing: ListingSnapshot, enrichment: Enrichment
    ) -> bool:
        price = listing.price_nano
        if prefs.min_price_nano is not None and (price is None or price < prefs.min_price_nano):
            return False
        if prefs.max_price_nano is not None and (price is None or price > prefs.max_price_nano):
            return False
        if prefs.collections:
            wanted = {normalize_name(c) for c in prefs.collections}
            names = {normalize_name(n) for n in (listing.collection_name, listing.collection_title) if n}
            if not wanted & names:
                return False
        if prefs.min_monochrome_share_percent is not None:
            share = enrichment.model_share.percent if enrichment.model_share else None
            if share is None or share < prefs.min_monochrome_share_percent:
                return False
        return True

    async def _keyboard(self, listing: ListingSnapshot, *, monochrome: bool) -> InlineKeyboardMarkup:
        token = await self.make_token(
            {"gift_id": listing.gift_id, "price": listing.price_nano, "raw": listing.raw}
        )
        first_row = [InlineKeyboardButton(text="🛒 Купить", callback_data=f"mb:{token}")]
        nft = texts.telegram_nft_url(listing)
        if nft:
            first_row.append(InlineKeyboardButton(text="🎁 В Telegram", url=nft))
        second_row = [InlineKeyboardButton(text="Подробнее", callback_data=f"ld:{token}")]
        mrkt = texts.listing_url(self.settings, listing)  # only when the exact gift link is configured
        if mrkt:
            second_row.append(InlineKeyboardButton(text="Открыть в MRKT", url=mrkt))
        return InlineKeyboardMarkup(inline_keyboard=[first_row, second_row])

    def _dedup_key(
        self, prefs: NotificationSettings, listing_id: int | None, gift_id: str, price: int | None, kind: str
    ) -> str:
        identity = f"L{listing_id}" if listing_id is not None else f"G{gift_id}"
        if prefs.no_repeats:
            return f"listing:{identity}"
        return f"{kind}:{identity}:{price}"

    async def listing_for_user(
        self,
        flags: UserFlags,
        listing: ListingSnapshot,
        enrichment: Enrichment,
        matched: list[FilterSpec],
        *,
        listing_id: int | None,
        price_drop_from: int | None = None,
    ) -> bool:
        if flags.is_blocked:
            return False
        prefs = flags.notify
        verdict = enrichment.verdict
        is_mono = verdict.status is MonochromeStatus.MONOCHROME
        in_scope = self._in_scope(prefs, listing, enrichment)

        if price_drop_from is not None:
            if not prefs.price_drops or listing.price_nano is None or price_drop_from <= 0:
                return False
            drop = (price_drop_from - listing.price_nano) / price_drop_from * 100
            if drop < prefs.price_drop_min_percent or not (matched or (prefs.all_listings and in_scope)):
                return False
            note = f"было {format_ton(price_drop_from)}, −{drop:.1f}%"
            status = (
                "подходит под фильтр: " + ", ".join(s.name for s in matched) if matched else "все листинги"
            )
            text = texts.new_listing_text(listing, enrichment, status_line=status, price_note=note)
            return await self.send(
                flags.user_id,
                text,
                kind="price_drop",
                keyboard=await self._keyboard(listing, monochrome=False),
                dedup_key=self._dedup_key(prefs, listing_id, listing.gift_id, listing.price_nano, "drop"),
                listing_id=listing_id,
                max_per_minute=prefs.max_per_minute,
                preview_url=texts.telegram_nft_url(listing),
            )

        mono_filters = [s for s in matched if s.kind is FilterKind.MONOCHROME]
        if matched and (prefs.matching_only or prefs.all_listings):
            if mono_filters and is_mono:
                text = texts.monochrome_text(listing, enrichment, filter_names=[s.name for s in matched])
                keyboard = await self._keyboard(listing, monochrome=True)
                kind = "monochrome"
            else:
                status = "подходит под фильтр: " + ", ".join(s.name for s in matched)
                text = texts.new_listing_text(listing, enrichment, status_line=status)
                keyboard = await self._keyboard(listing, monochrome=False)
                kind = "listing"
        elif is_mono and prefs.monochrome and in_scope:
            text = texts.monochrome_text(listing, enrichment, filter_names=[])
            keyboard = await self._keyboard(listing, monochrome=True)
            kind = "monochrome"
        elif prefs.all_listings and in_scope:
            text = texts.new_listing_text(listing, enrichment, status_line="не подходит под ваши фильтры")
            keyboard = await self._keyboard(listing, monochrome=False)
            kind = "listing"
        else:
            return False
        return await self.send(
            flags.user_id,
            text,
            kind=kind,
            keyboard=keyboard,
            dedup_key=self._dedup_key(prefs, listing_id, listing.gift_id, listing.price_nano, "listing"),
            listing_id=listing_id,
            max_per_minute=prefs.max_per_minute,
            preview_url=texts.telegram_nft_url(listing),
        )

    async def purchase_message(
        self,
        user_id: int,
        text: str,
        *,
        success: bool,
        prefs: NotificationSettings,
        dedup_key: str | None = None,
    ) -> None:
        if success and not prefs.purchases:
            return
        if not success and not prefs.errors:
            return
        await self.send(
            user_id,
            text,
            kind="purchase" if success else "purchase_error",
            critical=True,
            dedup_key=dedup_key,
        )
