"""Emergency stop and runtime run-mode control.

The emergency stop is stored in Redis (checked before every purchase step) and mirrored in PostgreSQL,
so it survives restarts even if Redis is flushed. The runtime run mode can only be lowered below the
RUN_MODE environment value, never raised above it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.repo import misc
from gift_sniper.metrics import KILL_SWITCH

log = logging.getLogger(__name__)

STATE_KILL = "kill_switch"
STATE_RUN_MODE = "run_mode"
STATE_POLL = "poll_interval"
POLL_LIMITS = (0.3, 10.0)  # seconds between MRKT feed polls that can be chosen


class ControlService:
    def __init__(
        self, settings: Settings, redis: Redis, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> None:
        self.settings = settings
        self.redis = redis
        self.sessionmaker = sessionmaker
        self.kill_key = f"{settings.redis_prefix}:kill_switch"
        self.mode_key = f"{settings.redis_prefix}:run_mode"
        self.poll_key = f"{settings.redis_prefix}:poll_interval"

    async def restore(self) -> None:
        """Copy the persisted state from PostgreSQL to Redis on startup."""
        async with self.sessionmaker() as session:
            kill = await misc.get_state(session, STATE_KILL)
            mode = await misc.get_state(session, STATE_RUN_MODE)
            poll = await misc.get_state(session, STATE_POLL)
        if kill and kill.get("active"):
            await self.redis.set(self.kill_key, "1")
        if mode and mode.get("mode"):
            await self.redis.set(self.mode_key, str(mode["mode"]))
        if poll and poll.get("seconds"):
            await self.redis.set(self.poll_key, str(poll["seconds"]))
        KILL_SWITCH.set(1 if await self.is_stopped() else 0)

    async def is_stopped(self) -> bool:
        try:
            return bool(await self.redis.get(self.kill_key))
        except Exception:
            log.exception("redis unavailable while checking the emergency stop; treating as STOPPED")
            return True  # fail safe: no purchases without a working stop switch

    async def stop_all(self, *, by_user: int | None, reason: str = "") -> None:
        await self.redis.set(self.kill_key, "1")
        async with self.sessionmaker() as session, session.begin():
            await misc.set_state(
                session, STATE_KILL, {"active": True, "by": by_user, "at": datetime.now(UTC).isoformat()}
            )
            await misc.audit(session, "emergency_stop", user_id=by_user, reason=reason)
        KILL_SWITCH.set(1)
        log.warning("EMERGENCY STOP activated", extra={"by": by_user, "reason": reason})

    async def resume(self, *, by_user: int | None) -> None:
        await self.redis.delete(self.kill_key)
        async with self.sessionmaker() as session, session.begin():
            await misc.set_state(
                session, STATE_KILL, {"active": False, "by": by_user, "at": datetime.now(UTC).isoformat()}
            )
            await misc.audit(session, "emergency_resume", user_id=by_user)
        KILL_SWITCH.set(0)

    async def run_mode(self) -> RunMode:
        """Effective mode = min(env RUN_MODE, runtime override)."""
        env_mode = self.settings.run_mode
        try:
            raw = await self.redis.get(self.mode_key)
        except Exception:
            return RunMode.NOTIFY_ONLY
        if raw:
            try:
                override = RunMode(raw.decode() if isinstance(raw, bytes) else raw)
            except ValueError:
                return env_mode
            return override if override.rank < env_mode.rank else env_mode
        return env_mode

    async def poll_interval(self) -> float:
        """Seconds between MRKT feed polls: chosen in the Mini App, else MRKT_FEED_POLL_INTERVAL_SECONDS."""
        default = self.settings.mrkt_feed_poll_interval_seconds
        try:
            raw = await self.redis.get(self.poll_key)
            value = float(raw) if raw else None
        except Exception:
            return default
        low, high = POLL_LIMITS
        return value if value is not None and low <= value <= high else default

    async def set_poll_interval(self, seconds: float, *, by_user: int | None) -> float:
        low, high = POLL_LIMITS
        if not low <= seconds <= high:
            raise ValueError(f"Интервал опроса должен быть от {low} до {high} с")
        await self.redis.set(self.poll_key, str(seconds))
        async with self.sessionmaker() as session, session.begin():
            await misc.set_state(session, STATE_POLL, {"seconds": seconds, "by": by_user})
            await misc.audit(session, "poll_interval", user_id=by_user, seconds=seconds)
        return seconds

    async def set_run_mode(self, mode: RunMode, *, by_user: int | None) -> RunMode:
        if mode.rank > self.settings.run_mode.rank:
            raise ValueError(f"Режим {mode.value} выше разрешённого RUN_MODE={self.settings.run_mode.value}")
        await self.redis.set(self.mode_key, mode.value)
        async with self.sessionmaker() as session, session.begin():
            await misc.set_state(session, STATE_RUN_MODE, {"mode": mode.value, "by": by_user})
            await misc.audit(session, "run_mode", user_id=by_user, mode=mode.value)
        return mode
