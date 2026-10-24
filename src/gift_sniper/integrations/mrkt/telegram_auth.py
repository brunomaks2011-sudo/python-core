"""MRKT Mini App initData via the operator's own Telegram session (Kurigram, the maintained Pyrogram fork).

This is the flow from the community documentation (boostNT/MRKT-API):
RequestAppWebView(bot=@mrkt, short_name="app") -> URL with tgWebAppData -> POST /auth {"data": initData}.

The interactive login (phone number, login code, 2FA password) happens only in the operator's terminal
via `python -m gift_sniper mrkt-login`; the bot never asks for Telegram credentials in chat and never
stores a password (Pyrogram keeps only the session authorization key). The session file grants full
access to the Telegram account: keep it private, and terminate it in Telegram -> Settings -> Devices
if it leaks.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from urllib.parse import unquote

MRKT_BOT_USERNAME = "mrkt"
MRKT_APP_SHORT_NAME = "app"


class TelegramSessionError(RuntimeError):
    pass


class TelegramSessionRevoked(TelegramSessionError):
    """Telegram no longer accepts the stored authorization (terminated in Settings -> Devices, expired)."""


SESSION_REVOKED_MESSAGE = (
    "Telegram session was terminated or expired: run `python -m gift_sniper mrkt-login` to log in again"
)


def session_parts(session_path: str) -> tuple[str, str]:
    """'data/mrkt' -> (workdir 'data', name 'mrkt'); Pyrogram stores it as data/mrkt.session."""
    path = Path(session_path)
    name = path.name[: -len(".session")] if path.name.endswith(".session") else path.name
    return str(path.parent if str(path.parent) else "."), name


def session_file(session_path: str) -> Path:
    workdir, name = session_parts(session_path)
    return Path(workdir) / f"{name}.session"


def extract_init_data(url: str) -> str:
    if "tgWebAppData=" not in url:
        raise TelegramSessionError("Telegram did not return tgWebAppData for the MRKT Mini App")
    return unquote(url.split("tgWebAppData=", 1)[1].split("&tgWebAppVersion", 1)[0])


async def fetch_init_data(
    *, api_id: int, api_hash: str, session_path: str, interactive: bool, use_qr: bool = False
) -> str:
    """Open the MRKT Mini App as the session's user and return its initData.

    With interactive=False an existing, authorized session is required: the call never prompts,
    so it is safe inside the running bot. use_qr logs a new session in by scanning a QR code with the
    Telegram app (Settings -> Devices) instead of typing a login code.
    """
    try:
        from pyrogram import Client
        from pyrogram.errors import (
            AuthKeyInvalid,
            AuthKeyPermEmpty,
            AuthKeyUnregistered,
            SessionExpired,
            SessionRevoked,
        )
        from pyrogram.raw.functions.messages import RequestAppWebView
        from pyrogram.raw.types import InputBotAppShortName, InputUser
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise TelegramSessionError("kurigram is not installed (pip install kurigram)") from exc
    revoked = (AuthKeyUnregistered, AuthKeyInvalid, AuthKeyPermEmpty, SessionExpired, SessionRevoked)

    workdir, name = _prepare_workdir(session_path, interactive=interactive)
    qr = interactive and use_qr
    # QR login waits for updateLoginToken, which a no-updates connection never receives
    client = Client(name, api_id=api_id, api_hash=api_hash, workdir=workdir, no_updates=not qr)
    if not interactive:
        # an existing session must already be authorized; never fall back to input() prompts
        is_authorized = await client.connect()
        try:
            if not is_authorized:
                raise TelegramSessionError(
                    "Telegram session is not authorized: run `python -m gift_sniper mrkt-login`"
                )
            return await _request_init_data(client, RequestAppWebView, InputBotAppShortName, InputUser)
        except revoked as exc:
            raise TelegramSessionRevoked(SESSION_REVOKED_MESSAGE) from exc
        finally:
            await client.disconnect()
    try:
        await client.start(use_qr=qr)  # interactive login in the operator's terminal when needed
    except revoked as exc:  # a stored session is used as is, without a new login
        raise TelegramSessionRevoked(SESSION_REVOKED_MESSAGE) from exc
    try:
        return await _request_init_data(client, RequestAppWebView, InputBotAppShortName, InputUser)
    finally:
        with contextlib.suppress(ConnectionError):
            await client.stop()


def discard_session(session_path: str) -> None:
    """Delete a session Telegram no longer accepts, so the next login starts from scratch."""
    path = session_file(session_path)
    for stale in (path, path.with_name(path.name + "-journal")):
        stale.unlink(missing_ok=True)


def _prepare_workdir(session_path: str, *, interactive: bool) -> tuple[str, str]:
    workdir, name = session_parts(session_path)
    if not interactive and not session_file(session_path).exists():
        raise TelegramSessionError(
            f"Telegram session {session_file(session_path)} not found: run `python -m gift_sniper mrkt-login`"
        )
    Path(workdir).mkdir(parents=True, exist_ok=True)
    return workdir, name


async def _request_init_data(
    client: Any, request_app_web_view: Any, input_bot_app_short_name: Any, input_user: Any
) -> str:
    peer = await client.resolve_peer(MRKT_BOT_USERNAME)
    bot = input_user(user_id=peer.user_id, access_hash=peer.access_hash)
    app = input_bot_app_short_name(bot_id=bot, short_name=MRKT_APP_SHORT_NAME)
    view = await client.invoke(request_app_web_view(peer=peer, app=app, platform="android"))
    return extract_init_data(view.url)
