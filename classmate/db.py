"""Подключение к SQLite и схема базы данных ClassMate."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name      TEXT NOT NULL,
    password_hash     TEXT NOT NULL,
    timezone          TEXT NOT NULL DEFAULT 'UTC',
    reminder_time     TEXT NOT NULL DEFAULT '18:00',
    remind_day_before INTEGER NOT NULL DEFAULT 1,
    remind_on_day     INTEGER NOT NULL DEFAULT 1,
    notify_new        INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    version     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Один пользователь состоит только в одном классе.
CREATE TABLE IF NOT EXISTS memberships (
    user_id   INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    class_id  INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    role      TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    joined_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memberships_class ON memberships(class_id);

CREATE TABLE IF NOT EXISTS homework (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    author_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    subject     TEXT NOT NULL,
    description TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    pages       TEXT NOT NULL DEFAULT '',
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_homework_class_due ON homework(class_id, due_date);

-- Отметка «выполнено» хранится для каждого пользователя отдельно.
CREATE TABLE IF NOT EXISTS completions (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    homework_id  INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, homework_id)
);

CREATE TABLE IF NOT EXISTS attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    homework_id   INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    stored_name   TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    mime_type     TEXT NOT NULL,
    size          INTEGER NOT NULL,
    uploaded_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_homework ON attachments(homework_id);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    homework_id INTEGER REFERENCES homework(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('new', 'day_before', 'due_today')),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    read_at     TEXT,
    -- UNIQUE не даёт создать одно и то же напоминание дважды (важно для фонового потока).
    UNIQUE (user_id, homework_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, id);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint   TEXT NOT NULL UNIQUE,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Открывает соединение. Для каждого потока/запроса создаётся своё соединение."""
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
