"""Who is calling the Mini App API: Telegram WebApp initData, validated as Telegram documents it.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app — the hash is an
HMAC-SHA256 keyed with HMAC-SHA256("WebAppData", bot token); aiogram implements exactly that check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram.utils.web_app import safe_parse_webapp_init_data


class WebAppAuthError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WebAppIdentity:
    user_id: int
    username: str | None
    full_name: str | None


def identify(init_data: str, *, bot_token: str, max_age: timedelta) -> WebAppIdentity:
    """The Telegram user of a valid, recent initData string; raises WebAppAuthError otherwise."""
    if not init_data:
        raise WebAppAuthError("Откройте приложение из Telegram")
    try:
        data = safe_parse_webapp_init_data(bot_token, init_data)
    except ValueError as exc:
        raise WebAppAuthError("Подпись Telegram не прошла проверку") from exc
    auth_date = data.auth_date if data.auth_date.tzinfo else data.auth_date.replace(tzinfo=UTC)
    if datetime.now(UTC) - auth_date > max_age:
        raise WebAppAuthError("Сессия приложения устарела: закройте и откройте его снова")
    user = data.user
    if user is None:
        raise WebAppAuthError("Telegram не передал пользователя")
    full_name = " ".join(part for part in (user.first_name, user.last_name) if part) or None
    return WebAppIdentity(user_id=int(user.id), username=user.username, full_name=full_name)
