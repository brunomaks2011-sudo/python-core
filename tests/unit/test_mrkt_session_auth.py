"""MRKT token from the operator's Telegram session: refresh on 401, cooldown, env file editing."""

from __future__ import annotations

import asyncio
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

from gift_sniper import __main__ as cli
from gift_sniper.envfile import mask, update_env_value
from gift_sniper.integrations.mrkt import MrktAuthError, MrktClient, telegram_auth
from gift_sniper.integrations.mrkt.telegram_auth import (
    TelegramSessionError,
    TelegramSessionRevoked,
    extract_init_data,
    session_file,
    session_parts,
)
from tests.factories import make_settings
from tests.fake_server import FakeServer, Reply

API = "/api/v1/"


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeServer]:
    srv = FakeServer()
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
def session_path(tmp_path: Path) -> str:
    path = tmp_path / "data" / "mrkt"
    path.parent.mkdir(parents=True)
    (path.parent / "mrkt.session").write_bytes(b"fake session")
    return str(path)


def test_session_paths() -> None:
    assert session_parts("data/mrkt") == ("data", "mrkt")
    assert session_parts("data/mrkt.session") == ("data", "mrkt")
    assert session_parts("mrkt") == (".", "mrkt")
    assert session_file("data/mrkt") == Path("data/mrkt.session")


def test_extract_init_data() -> None:
    url = "https://cdn.tgmrkt.io/#tgWebAppData=query_id%3DAAA%26user%3D%257B%257D&tgWebAppVersion=8.0&x=1"
    assert extract_init_data(url) == "query_id=AAA&user=%7B%7D"
    with pytest.raises(TelegramSessionError):
        extract_init_data("https://cdn.tgmrkt.io/#nothing")


def test_session_availability_requires_credentials_and_file(session_path: str, tmp_path: Path) -> None:
    assert make_settings(
        telegram_api_id=1, telegram_api_hash="h", mrkt_telegram_session=session_path
    ).mrkt_session_available
    assert not make_settings(
        telegram_api_id=None, telegram_api_hash="h", mrkt_telegram_session=session_path
    ).mrkt_session_available
    missing = str(tmp_path / "nowhere" / "mrkt")
    assert not make_settings(
        telegram_api_id=1, telegram_api_hash="h", mrkt_telegram_session=missing
    ).mrkt_session_available
    s = make_settings(
        mrkt_access_token=None, telegram_api_id=1, telegram_api_hash="h", mrkt_telegram_session=session_path
    )
    assert s.mrkt_configured


def test_empty_api_id_from_env_is_none() -> None:
    assert make_settings(telegram_api_id="", telegram_api_hash="").telegram_api_id is None


async def test_non_interactive_fetch_never_prompts_without_session(tmp_path: Path) -> None:
    with pytest.raises(TelegramSessionError, match="mrkt-login"):
        await telegram_auth.fetch_init_data(
            api_id=1, api_hash="h", session_path=str(tmp_path / "none" / "mrkt"), interactive=False
        )


async def test_token_is_refreshed_from_session_on_401(
    server: FakeServer, session_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    async def fake_fetch(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        return "init-from-session"

    monkeypatch.setattr(telegram_auth, "fetch_init_data", fake_fetch)
    server.add("GET", API + "me", Reply(status=401), Reply(body={"id": 42}))
    server.add("POST", API + "auth", Reply(body={"token": "fresh"}))
    client = MrktClient(
        make_settings(
            mrkt_api_base_url=server.url + "/api/v1",
            mrkt_access_token="expired",
            telegram_api_id=1,
            telegram_api_hash="hash",
            mrkt_telegram_session=session_path,
        )
    )
    await client.start()
    try:
        assert await client.me() == {"id": 42}
    finally:
        await client.close()
    assert calls and calls[0]["interactive"] is False and calls[0]["session_path"] == session_path
    assert server.calls("POST", API + "auth")[0].json == {"data": "init-from-session"}
    me_calls = server.calls("GET", API + "me")
    assert [c.headers["Authorization"] for c in me_calls] == ["expired", "fresh"]
    assert client.token == "fresh"


async def test_concurrent_401s_trigger_a_single_reauthorization(
    server: FakeServer, session_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetches = 0

    async def fake_fetch(**kwargs: object) -> str:
        nonlocal fetches
        fetches += 1
        await asyncio.sleep(0.05)
        return "init"

    monkeypatch.setattr(telegram_auth, "fetch_init_data", fake_fetch)
    server.add("GET", API + "balance", Reply(status=401), Reply(status=401), Reply(body={"hard": 1}))
    server.add("POST", API + "auth", Reply(body={"token": "fresh"}))
    client = MrktClient(
        make_settings(
            mrkt_api_base_url=server.url + "/api/v1",
            mrkt_access_token="expired",
            telegram_api_id=1,
            telegram_api_hash="hash",
            mrkt_telegram_session=session_path,
        )
    )
    await client.start()
    try:
        results = await asyncio.gather(client.balance_nano(), client.balance_nano())
    finally:
        await client.close()
    assert results == [1, 1]
    assert fetches == 1 and len(server.calls("POST", API + "auth")) == 1


async def test_reauthorization_cooldown(
    server: FakeServer, session_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(**kwargs: object) -> str:
        return "init"

    monkeypatch.setattr(telegram_auth, "fetch_init_data", fake_fetch)
    server.add("GET", API + "me", Reply(status=401))  # MRKT keeps rejecting every token
    server.add("POST", API + "auth", Reply(body={"token": "still-rejected"}))
    client = MrktClient(
        make_settings(
            mrkt_api_base_url=server.url + "/api/v1",
            mrkt_access_token="expired",
            telegram_api_id=1,
            telegram_api_hash="hash",
            mrkt_telegram_session=session_path,
            mrkt_auth_cooldown_seconds=60,
        )
    )
    await client.start()
    try:
        with pytest.raises(MrktAuthError):
            await client.me()  # one re-authorization, then the new token is rejected too
        with pytest.raises(MrktAuthError, match="через"):
            await client.me()  # no second re-authorization inside the cooldown
    finally:
        await client.close()
    assert len(server.calls("POST", API + "auth")) == 1


async def test_login_succeeds_when_balance_is_unavailable(
    server: FakeServer,
    session_path: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_fetch(**kwargs: object) -> str:
        return "init-from-login"

    settings = make_settings(
        mrkt_api_base_url=server.url + "/api/v1",
        mrkt_access_token=None,
        telegram_api_id=1,
        telegram_api_hash="hash",
        mrkt_telegram_session=session_path,
    )
    monkeypatch.setattr(telegram_auth, "fetch_init_data", fake_fetch)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    server.add("POST", API + "auth", Reply(body={"token": "fresh-token-123456"}))
    server.add("GET", API + "balance", Reply(status=404, body={"error": "not found"}))
    assert await cli.mrkt_login(None, show=False) == 0
    out = capsys.readouterr().out
    assert "✅ Токен MRKT получен: fres…3456" in out and "нет данных" in out
    assert server.calls("POST", API + "auth")[0].json == {"data": "init-from-login"}


class FakeTelegramClient:
    def __init__(self, kwargs: dict[str, object]) -> None:
        self.kwargs = kwargs
        self.started_with: dict[str, object] | None = None
        self.stopped = False

    async def start(self, **kwargs: object) -> FakeTelegramClient:
        self.started_with = kwargs
        return self

    async def stop(self) -> None:
        self.stopped = True

    async def resolve_peer(self, username: str) -> SimpleNamespace:
        return SimpleNamespace(user_id=1, access_hash=2)

    async def invoke(self, query: object) -> SimpleNamespace:
        return SimpleNamespace(url="https://cdn.tgmrkt.io/#tgWebAppData=a%3D1&tgWebAppVersion=8.0")


async def test_qr_login_uses_a_connection_with_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clients: list[FakeTelegramClient] = []

    def make_client(name: str, **kwargs: object) -> FakeTelegramClient:
        clients.append(FakeTelegramClient(kwargs))
        return clients[-1]

    # imported lazily: importing pyrogram outside a running loop emits a DeprecationWarning
    monkeypatch.setattr("pyrogram.Client", make_client)
    for use_qr in (False, True):
        init_data = await telegram_auth.fetch_init_data(
            api_id=1,
            api_hash="h",
            session_path=str(tmp_path / "data" / "mrkt"),
            interactive=True,
            use_qr=use_qr,
        )
        assert init_data == "a=1"
    # updateLoginToken (QR scanned) never reaches a no-updates connection
    assert [c.kwargs["no_updates"] for c in clients] == [True, False]
    assert [c.started_with for c in clients] == [{"use_qr": False}, {"use_qr": True}]
    assert all(c.stopped for c in clients)


class TerminatedTelegramClient(FakeTelegramClient):
    """The session file still says "authorized", but the user terminated it in Telegram -> Devices."""

    async def start(self, **kwargs: object) -> FakeTelegramClient:
        from pyrogram.errors import AuthKeyUnregistered

        raise AuthKeyUnregistered()

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        self.stopped = True

    async def resolve_peer(self, username: str) -> SimpleNamespace:
        from pyrogram.errors import AuthKeyUnregistered

        raise AuthKeyUnregistered()


async def test_terminated_session_is_reported_as_revoked(
    session_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pyrogram.Client", lambda name, **kwargs: TerminatedTelegramClient(kwargs))
    for interactive in (True, False):
        with pytest.raises(TelegramSessionRevoked, match="mrkt-login"):
            await telegram_auth.fetch_init_data(
                api_id=1, api_hash="h", session_path=session_path, interactive=interactive
            )


async def test_login_discards_a_terminated_session_and_starts_over(
    server: FakeServer,
    session_path: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_existed: list[bool] = []

    async def fake_fetch(**kwargs: object) -> str:
        session_existed.append(session_file(session_path).exists())
        if len(session_existed) == 1:
            raise TelegramSessionRevoked("terminated")
        return "init-after-new-login"

    settings = make_settings(
        mrkt_api_base_url=server.url + "/api/v1",
        mrkt_access_token=None,
        telegram_api_id=1,
        telegram_api_hash="hash",
        mrkt_telegram_session=session_path,
    )
    monkeypatch.setattr(telegram_auth, "fetch_init_data", fake_fetch)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    server.add("POST", API + "auth", Reply(body={"token": "fresh-token-123456"}))
    server.add("GET", API + "balance", Reply(body={"hard": 1}))
    assert await cli.mrkt_login(None, show=False) == 0
    assert session_existed == [True, False]  # the stale file is gone before the new login
    assert "начинаю вход заново" in capsys.readouterr().out
    assert server.calls("POST", API + "auth")[0].json == {"data": "init-after-new-login"}


def test_cli_passes_the_qr_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, bool, bool]] = []

    async def fake_login(env_path: str | None, show: bool, use_qr: bool = False) -> int:
        calls.append((env_path, show, use_qr))
        return 0

    monkeypatch.setattr(cli, "get_settings", make_settings)
    monkeypatch.setattr(cli, "setup_logging", lambda *args: None)
    monkeypatch.setattr(cli, "mrkt_login", fake_login)
    assert cli.main(["mrkt-login", "--qr"]) == 0
    assert cli.main(["mrkt-login"]) == 0
    assert calls == [(None, False, True), (None, False, False)]


def test_update_env_value(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nMRKT_ACCESS_TOKEN=\nOTHER=1\n", encoding="utf-8")
    update_env_value(env, "MRKT_ACCESS_TOKEN", "abc")
    update_env_value(env, "NEW_KEY", "x")
    assert env.read_text(encoding="utf-8") == "# comment\nMRKT_ACCESS_TOKEN=abc\nOTHER=1\nNEW_KEY=x\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        update_env_value(env, "K", "a\nb")


def test_mask() -> None:
    assert mask("1234567890abcdef") == "1234…cdef"
    assert mask("short") == "*****"
