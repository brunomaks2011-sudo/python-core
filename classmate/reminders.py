"""Напоминания о домашних заданиях, уведомления в приложении и Web Push.

Логика простая и устойчивая к повторам:
* каждое напоминание записывается в таблицу notifications с уникальным ключом
  (пользователь, задание, вид), поэтому его не создать дважды, даже если проверка
  запускается из нескольких мест (фоновый поток, запросы пользователей, несколько процессов);
* push-уведомление отправляется только тогда, когда запись действительно создана.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import db as dbm

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pywebpush не установлен: сайт работает, только без Web Push
    webpush = None
    WebPushException = Exception

log = logging.getLogger("classmate")

PUSH_URL = "/#/notifications"


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def user_zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def excerpt(text: str, limit: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_due(due: str) -> str:
    return date.fromisoformat(due).strftime("%d.%m.%Y")


def insert_notification(conn, user_id, homework_id, kind, title, body, now) -> dict | None:
    """Создаёт уведомление. Возвращает его данные, если запись новая, иначе None."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO notifications
           (user_id, homework_id, kind, title, body, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, homework_id, kind, title, body, iso(now)),
    )
    if cur.rowcount != 1:
        return None
    return {
        "user_id": user_id,
        "homework_id": homework_id,
        "kind": kind,
        "title": title,
        "body": body,
    }


def new_homework_notifications(
    conn, class_id, homework_id, author_id, author_name, subject, description, due_date, now
) -> list[dict]:
    """Сообщает всем одноклассникам (кроме автора) о новом задании. Коммит делает вызывающий код."""
    recipients = conn.execute(
        """SELECT u.id FROM memberships m
           JOIN users u ON u.id = m.user_id
           WHERE m.class_id = ? AND u.id <> ? AND u.notify_new = 1""",
        (class_id, author_id),
    ).fetchall()
    title = f"Новое задание: {subject}"
    body = f"{author_name} · сдать до {format_due(due_date)} · {excerpt(description)}"
    created = []
    for row in recipients:
        item = insert_notification(conn, row["id"], homework_id, "new", title, body, now)
        if item:
            created.append(item)
    return created


def run_reminders(conn, now: datetime, user_id: int | None = None) -> list[dict]:
    """Создаёт напоминания «за день» и «в день сдачи», если наступило выбранное пользователем время.

    Время считается по часовому поясу пользователя. Задания, которые он уже отметил
    как выполненные, не напоминаются.
    """
    today = now.astimezone(timezone.utc).date()
    sql = """
        SELECT u.id AS user_id, u.timezone, u.reminder_time,
               u.remind_day_before, u.remind_on_day,
               h.id AS homework_id, h.subject, h.description, h.due_date
        FROM memberships m
        JOIN users u ON u.id = m.user_id
        JOIN homework h ON h.class_id = m.class_id
        WHERE h.due_date BETWEEN ? AND ?
          AND (u.remind_day_before = 1 OR u.remind_on_day = 1)
          AND NOT EXISTS (
                SELECT 1 FROM completions c
                WHERE c.user_id = u.id AND c.homework_id = h.id)
    """
    params: list = [
        (today - timedelta(days=2)).isoformat(),
        (today + timedelta(days=3)).isoformat(),
    ]
    if user_id is not None:
        sql += " AND u.id = ?"
        params.append(user_id)

    created: list[dict] = []
    for row in conn.execute(sql, params).fetchall():
        local = now.astimezone(user_zone(row["timezone"]))
        hours, minutes = (int(part) for part in row["reminder_time"].split(":"))
        if local.time() < time(hours, minutes):
            continue

        due = date.fromisoformat(row["due_date"])
        kinds = []
        if row["remind_day_before"] and local.date() == due - timedelta(days=1):
            kinds.append("day_before")
        if row["remind_on_day"] and local.date() == due:
            kinds.append("due_today")

        for kind in kinds:
            if kind == "day_before":
                title = f"Завтра сдавать: {row['subject']}"
            else:
                title = f"Сегодня сдавать: {row['subject']}"
            item = insert_notification(
                conn,
                row["user_id"],
                row["homework_id"],
                kind,
                title,
                excerpt(row["description"]),
                now,
            )
            if item:
                created.append(item)
    conn.commit()
    return created


class PushService:
    """Отправка Web Push. Ключи VAPID создаются один раз и хранятся в папке данных."""

    def __init__(self, db_path, key_path, subject: str) -> None:
        self.db_path = str(db_path)
        self.key_path = Path(key_path)
        self.subject = subject
        self.public_key: str | None = None
        self.enabled = webpush is not None
        if self.enabled:
            try:
                self._load_or_create_keys()
            except Exception:
                log.exception("Не удалось подготовить ключи VAPID, push-уведомления отключены")
                self.enabled = False

    def _load_or_create_keys(self) -> None:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        from py_vapid import Vapid01

        if self.key_path.exists():
            vapid = Vapid01.from_file(str(self.key_path))
        else:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            vapid = Vapid01()
            vapid.generate_keys()
            vapid.save_key(str(self.key_path))
            os.chmod(self.key_path, 0o600)
        raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        self.public_key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def send_async(self, items: list[dict]) -> None:
        """Отправляет уведомления в фоне, чтобы не задерживать ответ пользователю."""
        if not self.enabled or not items:
            return
        threading.Thread(target=self._deliver, args=(list(items),), daemon=True).start()

    def _deliver(self, items: list[dict]) -> None:
        try:
            with closing(dbm.connect(self.db_path)) as conn:
                for item in items:
                    subs = conn.execute(
                        "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?",
                        (item["user_id"],),
                    ).fetchall()
                    if not subs:
                        continue
                    tag = f"hw-{item['homework_id']}" if item.get("homework_id") else "classmate"
                    payload = json.dumps(
                        {"title": item["title"], "body": item["body"], "url": PUSH_URL, "tag": tag}
                    )
                    for sub in subs:
                        if not self._send_one(sub, payload):
                            conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub["id"],))
                conn.commit()
        except Exception:
            log.exception("Ошибка отправки push-уведомлений")

    def _send_one(self, sub, payload: str) -> bool:
        """Возвращает False, если подписка больше не действительна и её надо удалить."""
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=str(self.key_path),
                vapid_claims={"sub": self.subject},
                ttl=24 * 3600,
            )
            return True
        except WebPushException as exc:
            status = exc.response.status_code if getattr(exc, "response", None) is not None else None
            if status in (404, 410):
                return False
            log.warning("Push не доставлен (статус %s): %s", status, exc)
            return True


class ReminderScheduler(threading.Thread):
    """Фоновая проверка напоминаний (раз в минуту)."""

    def __init__(self, db_path, push: PushService, clock, interval: float = 60.0) -> None:
        super().__init__(name="classmate-reminders", daemon=True)
        self.db_path = str(db_path)
        self.push = push
        self.clock = clock
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self.run_once()

    def run_once(self) -> list[dict]:
        try:
            with closing(dbm.connect(self.db_path)) as conn:
                created = run_reminders(conn, self.clock())
            self.push.send_async(created)
            return created
        except Exception:
            log.exception("Ошибка при проверке напоминаний")
            return []

    def stop(self) -> None:
        self._stop_event.set()
