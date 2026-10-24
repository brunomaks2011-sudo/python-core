"""Minimal .env editing (used by `mrkt-login --write-env`)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def update_env_value(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a .env file, keeping every other line (and comments) as is."""
    if "\n" in value or "\r" in value:
        raise ValueError("value must be a single line")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
    replaced = False
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = f"{key}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)  # the file holds secrets


def mask(secret: str, keep: int = 4) -> str:
    if len(secret) <= keep * 2:
        return "*" * len(secret)
    return f"{secret[:keep]}…{secret[-keep:]}"
