"""Cached view of enabled filters and per-user flags for the hot path (listing processing)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.db.models import User, UserSettings
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.services.filters import FilterSpec
from gift_sniper.services.user_prefs import NotificationSettings


@dataclass(frozen=True, slots=True)
class UserFlags:
    user_id: int
    can_purchase: bool
    is_blocked: bool
    autobuy_enabled: bool
    monochrome_autobuy_enabled: bool
    purchases_paused: bool
    notify: NotificationSettings


class FilterCache:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        prefix: str,
        ttl: float = 10.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.version_key = f"{prefix}:filters:version"
        self.ttl = ttl
        self._loaded_at = 0.0
        self._version: str | None = None
        self._specs: list[FilterSpec] = []
        self._users: dict[int, UserFlags] = {}
        self._lock = asyncio.Lock()

    async def invalidate(self) -> None:
        self._loaded_at = 0.0
        if self.redis is not None:
            await self.redis.incr(self.version_key)

    async def _current_version(self) -> str | None:
        if self.redis is None:
            return None
        raw = await self.redis.get(self.version_key)
        return raw.decode() if isinstance(raw, bytes) else raw

    async def get(self) -> tuple[list[FilterSpec], dict[int, UserFlags]]:
        version = await self._current_version()
        fresh = time.monotonic() - self._loaded_at < self.ttl and version == self._version
        if fresh:
            return self._specs, self._users
        async with self._lock:
            async with self.sessionmaker() as session:
                specs = await filters_repo.load_enabled_specs(session)
                rows = (await session.execute(select(User, UserSettings).join(UserSettings))).all()
            users = {
                user.id: UserFlags(
                    user_id=user.id,
                    can_purchase=user.can_purchase,
                    is_blocked=user.is_blocked,
                    autobuy_enabled=prefs.autobuy_enabled,
                    monochrome_autobuy_enabled=prefs.monochrome_autobuy_enabled,
                    purchases_paused=prefs.purchases_paused,
                    notify=NotificationSettings.model_validate(prefs.notify or {}),
                )
                for user, prefs in rows
            }
            self._specs, self._users = specs, users
            self._loaded_at = time.monotonic()
            self._version = version
        return self._specs, self._users
