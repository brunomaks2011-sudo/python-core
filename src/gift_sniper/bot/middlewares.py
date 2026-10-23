"""Access control, user registration and flood protection for incoming updates."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from gift_sniper.db.repo import users as users_repo
from gift_sniper.services.container import Services


class AccessMiddleware(BaseMiddleware):
    """Only users listed in ADMIN_USER_IDS / ALLOWED_USER_IDS may use the bot."""

    def __init__(self, services: Services) -> None:
        self.services = services
        self.max_events = services.settings.bot_flood_max_events
        self.per_seconds = services.settings.bot_flood_window_seconds
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._registered: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return None
        settings = self.services.settings
        if not settings.is_allowed(user.id):
            if isinstance(event, Message):
                await event.answer(
                    f"⛔ Доступ запрещён. Попросите администратора добавить ваш ID: <code>{user.id}</code>"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён", show_alert=True)
            return None
        now = time.monotonic()
        window = self._events[user.id]
        while window and now - window[0] > self.per_seconds:
            window.popleft()
        if len(window) >= self.max_events:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком часто, подождите секунду")
            return None
        window.append(now)
        if now - self._registered.get(user.id, 0) > 600:
            async with self.services.sessionmaker() as session, session.begin():
                await users_repo.ensure_user(
                    session,
                    user.id,
                    username=user.username,
                    full_name=user.full_name,
                    is_admin=settings.is_admin(user.id),
                    can_purchase=settings.can_purchase(user.id),
                )
            self._registered[user.id] = now
        data["services"] = self.services
        data["is_admin"] = settings.is_admin(user.id)
        data["can_purchase"] = settings.can_purchase(user.id)
        return await handler(event, data)
