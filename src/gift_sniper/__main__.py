"""Command line entry point.

python -m gift_sniper run [--components bot,monitor,processor,buyer,scheduler,metrics]
python -m gift_sniper migrate
python -m gift_sniper sync-giftwiki
python -m gift_sniper check
"""

from __future__ import annotations

import argparse
import asyncio
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
    return 2


if __name__ == "__main__":
    sys.exit(main())
