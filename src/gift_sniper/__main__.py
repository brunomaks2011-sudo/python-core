"""Command line entry point.

python -m gift_sniper run [--components bot,monitor,processor,buyer,scheduler,metrics]
python -m gift_sniper migrate
python -m gift_sniper sync-giftwiki
python -m gift_sniper check
python -m gift_sniper mrkt-login [--write-env .env] [--show] [--qr]
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import os
import sys
from pathlib import Path

from gift_sniper.config import get_settings
from gift_sniper.logging_setup import setup_logging

log = logging.getLogger("gift_sniper")


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    candidates = [Path(os.environ["ALEMBIC_INI"])] if os.environ.get("ALEMBIC_INI") else []
    candidates += [Path.cwd() / "alembic.ini", Path(__file__).resolve().parents[2] / "alembic.ini"]
    ini = next((path for path in candidates if path.exists()), None)
    if ini is None:
        raise SystemExit("alembic.ini not found (set ALEMBIC_INI)")
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "migrations"))
    config.attributes["database_url"] = get_settings().database_url
    config.attributes["skip_logging"] = True
    command.upgrade(config, "head")
    print("migrations applied")


async def run(components: set[str]) -> None:
    from gift_sniper.app import Application

    await Application(get_settings()).run(components)


async def sync_giftwiki() -> int:
    from gift_sniper.app import Application

    app = Application(get_settings())
    services = await app.build()
    try:
        report = await services.sync.run(trigger="manual")
        print(
            f"status={report.status} pages={report.pages} records={report.records} gifts={report.gifts} "
            f"added={report.added} removed={report.removed} lookups={report.lookups_done}/"
            f"{report.lookups_done + report.lookups_failed} error={report.error}"
        )
        return 0 if report.status in ("success", "partial") else 1
    finally:
        await app.shutdown()


LOGIN_HINT_CODE = (
    "Если сессии ещё нет, Telegram запросит номер телефона, код входа и пароль 2FA (если включён).\n"
    "Они вводятся только в этом терминале и отправляются напрямую в Telegram; бот их не получает и не хранит.\n"
    "Вопросы задаёт библиотека Pyrogram на английском:\n"
    "  Enter phone number or bot token - номер с + и кодом страны\n"
    '  Is "..." correct? (y/N)         - латинская y в английской раскладке, иначе номер спросят снова\n'
    "  Enter confirmation code         - код из чата «Telegram» в приложении Telegram\n"
    "  Enter 2FA password              - облачный пароль, если включена двухэтапная проверка\n"
    "Код не пришёл? Вход без кода: mrkt-login --qr"
)
LOGIN_HINT_QR = (
    "Если сессии ещё нет, появится QR-код. В Telegram на телефоне: Настройки → Устройства →\n"
    "«Подключить устройство», затем наведите камеру на код (он обновляется примерно раз в 30 секунд).\n"
    "Если включена двухэтапная проверка, затем спросит облачный пароль (Enter 2FA password).\n"
    "Он вводится только в этом терминале и отправляется напрямую в Telegram; бот его не получает и не хранит."
)


async def mrkt_login(env_path: str | None, show: bool, use_qr: bool = False) -> int:
    """Create the operator's Telegram session (interactive, in this terminal) and obtain a MRKT token.

    The flow is the one from the MRKT community documentation: RequestAppWebView(@mrkt, "app") ->
    tgWebAppData -> POST /auth. Phone number, login code and 2FA password are typed only here and go
    straight to Telegram; the bot never receives them.
    """
    from pydantic import SecretStr

    from gift_sniper.domain.money import format_ton
    from gift_sniper.envfile import mask, update_env_value
    from gift_sniper.integrations.mrkt import MrktClient, MrktError
    from gift_sniper.integrations.mrkt.telegram_auth import (
        TelegramSessionRevoked,
        discard_session,
        fetch_init_data,
        session_file,
    )

    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        print(
            "Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env "
            "(https://my.telegram.org → API development tools) и запустите команду снова."
        )
        return 2
    print(f"Telegram-сессия: {session_file(settings.mrkt_telegram_session)}")
    print(LOGIN_HINT_QR if use_qr else LOGIN_HINT_CODE)
    login = functools.partial(
        fetch_init_data,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash.get_secret_value(),
        session_path=settings.mrkt_telegram_session,
        interactive=True,
        use_qr=use_qr,
    )
    try:
        try:
            init_data = await login()
        except TelegramSessionRevoked:
            print(
                "Сохранённая Telegram-сессия больше не действует (её завершили в Telegram → Настройки → "
                "Устройства или она истекла). Удаляю её и начинаю вход заново."
            )
            discard_session(settings.mrkt_telegram_session)
            init_data = await login()
    except Exception as exc:
        print(f"❌ Не удалось открыть MRKT через Telegram: {exc}")
        return 1
    client = MrktClient(
        settings.model_copy(update={"mrkt_access_token": None, "mrkt_init_data": SecretStr(init_data)})
    )
    await client.start()
    try:
        token = await client.obtain_token()
        try:
            balance = format_ton(await client.balance_nano())
        except MrktError as exc:  # informational only: the token and the session are what matter
            balance = f"нет данных ({exc})"
    except MrktError as exc:
        print(f"❌ MRKT не выдал токен: {exc}")
        return 1
    finally:
        await client.close()
    print(f"✅ Токен MRKT получен: {mask(token)}; баланс MRKT: {balance}")
    print(
        "Пока сессия существует, бот сам получает и обновляет токен (MRKT_ACCESS_TOKEN можно не задавать).\n"
        "Сессия даёт полный доступ к аккаунту Telegram: храните её в тайне; завершить её можно в "
        "Telegram → Настройки → Устройства."
    )
    if env_path:
        update_env_value(Path(env_path), "MRKT_ACCESS_TOKEN", token)
        print(f"MRKT_ACCESS_TOKEN записан в {env_path}")
    if show:
        print(token)
    return 0


async def check() -> int:
    from gift_sniper.selfcheck import run_selfcheck

    return await run_selfcheck(get_settings())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gift_sniper")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="run the bot and workers")
    run_parser.add_argument(
        "--components",
        default="bot,monitor,processor,buyer,scheduler,metrics",
        help="comma-separated subset of: bot, monitor, processor, buyer, scheduler, metrics",
    )
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("sync-giftwiki", help="run one Gift Wiki synchronization")
    sub.add_parser("check", help="check access to MRKT and Gift Wiki and report what works")
    login_parser = sub.add_parser(
        "mrkt-login", help="create the Telegram session and obtain a MRKT token (interactive, run once)"
    )
    login_parser.add_argument(
        "--write-env", default=None, help="also write MRKT_ACCESS_TOKEN into this .env file"
    )
    login_parser.add_argument("--show", action="store_true", help="print the full token")
    login_parser.add_argument(
        "--qr", action="store_true", help="log in by scanning a QR code in the Telegram app (no login code)"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)
    if args.command == "migrate":
        migrate()
        return 0
    if args.command == "run":
        components = {c.strip() for c in args.components.split(",") if c.strip()}
        asyncio.run(run(components))
        return 0
    if args.command == "sync-giftwiki":
        return asyncio.run(sync_giftwiki())
    if args.command == "check":
        return asyncio.run(check())
    if args.command == "mrkt-login":
        return asyncio.run(mrkt_login(args.write_env, args.show, args.qr))
    return 2


if __name__ == "__main__":
    sys.exit(main())
