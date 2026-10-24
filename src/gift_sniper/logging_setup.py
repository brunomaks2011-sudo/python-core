"""Structured logging with secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}]+(?:\s+[^'\"\s,}]+)?)"),
    re.compile(r"(?i)(x-api-key['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}]+)"),
    re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}]+)"),
    re.compile(r"(\d{6,12}:[A-Za-z0-9_-]{30,})"),  # Telegram bot token
]

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        replacement = (lambda m: m.group(1) + "***") if pattern.groups >= 2 else "***"
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            text += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        return redact(text)


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # pyrogram logs every MTProto connection step at INFO, which also breaks up the mrkt-login prompts
    for noisy in ("aiohttp.access", "asyncio", "pyrogram"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # a token refresh is a few MTProto calls: the pure-Python crypto fallback is fast enough
    logging.getLogger("pyrogram.crypto.aes").setLevel(logging.ERROR)
