"""Mini App callers are identified only by Telegram-signed, recent initData."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from urllib.parse import urlencode

import pytest

from gift_sniper.webapp.auth import WebAppAuthError, identify

TOKEN = "123456:TEST-TOKEN"
DAY = timedelta(hours=24)


def make_init_data(token: str = TOKEN, user_id: int = 1, *, auth_date: int | None = None) -> str:
    """initData signed the way Telegram documents it (independent of aiogram's implementation)."""
    fields = {
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "Ann", "last_name": "Lee", "username": "ann"}),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_init_data_identifies_the_user() -> None:
    who = identify(make_init_data(user_id=42), bot_token=TOKEN, max_age=DAY)
    assert (who.user_id, who.username, who.full_name) == (42, "ann", "Ann Lee")


@pytest.mark.parametrize(
    ("init_data", "message"),
    [
        ("", "из Telegram"),
        (make_init_data(token="999:OTHER"), "Подпись"),  # signed for another bot
        (make_init_data().replace("Ann", "Bob"), "Подпись"),  # tampered
        (make_init_data(auth_date=int(time.time()) - 2 * 24 * 3600), "устарела"),
    ],
)
def test_invalid_init_data_is_rejected(init_data: str, message: str) -> None:
    with pytest.raises(WebAppAuthError, match=message):
        identify(init_data, bot_token=TOKEN, max_age=DAY)
