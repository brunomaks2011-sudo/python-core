"""ClassMate: общий сервис домашних заданий для школьного класса.

Запуск для разработки:  python app.py   и открыть http://localhost:8000
"""

from __future__ import annotations

import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    Flask,
    current_app,
    g,
    jsonify,
    request,
    send_from_directory,
    session,
)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbm
from reminders import (
    PushService,
    ReminderScheduler,
    iso,
    new_homework_notifications,
    run_reminders,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS = 6
SUBJECT_MAX = 40
DESCRIPTION_MAX = 2000
PAGES_MAX = 200
COMMENT_MAX = 1000
CLASS_NAME_MAX = 60
NAME_MAX = 40
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,32}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# Без похожих символов (0/O, 1/I), чтобы код легко переписать с доски.
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; manifest-src 'self'; "
    "worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
HTTP_MESSAGES = {
    404: "Не найдено",
    405: "Метод не поддерживается",
    413: "Файл слишком большой (максимум 5 МБ)",
}

mimetypes.add_type("application/manifest+json", ".webmanifest")

USER_SQL = """
SELECT u.*, m.class_id, m.role, c.name AS class_name
FROM users u
LEFT JOIN memberships m ON m.user_id = u.id
LEFT JOIN classes c ON c.id = m.class_id
WHERE u.id = ?
"""


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


class AttemptLimiter:
    """Защита от перебора паролей и кодов: ограничивает число неудач за окно времени."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        recent = [moment for moment in self._hits.get(key, []) if now - moment < self.window]
        if recent:
            self._hits[key] = recent
        else:
            self._hits.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            recent = self._recent(key)
            recent.append(time.monotonic())
            self._hits[key] = recent

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


api_bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------- helpers

def now_utc() -> datetime:
    return current_app.extensions["clock"]()


def read_json() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Некорректный запрос")
    return data


def read_text(data: dict, key: str, label: str, max_len: int, required: bool = False) -> str:
    value = data.get(key)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ApiError(400, f"Поле «{label}» заполнено неверно")
    value = value.strip()
    if required and not value:
        raise ApiError(400, f"Заполните поле «{label}»")
    if len(value) > max_len:
        raise ApiError(400, f"Поле «{label}» слишком длинное (до {max_len} символов)")
    return value


def read_password(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or len(value) < 6:
        raise ApiError(400, "Пароль должен быть не короче 6 символов")
    if len(value) > 200:
        raise ApiError(400, "Пароль слишком длинный")
    return value


def read_username(data: dict) -> str:
    username = read_text(data, "username", "Логин", 32, required=True)
    if not USERNAME_RE.match(username):
        raise ApiError(
            400,
            "Логин: от 3 до 32 символов, латинские буквы, цифры, точка или подчёркивание",
        )
    return username.lower()


def read_timezone(value) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        ZoneInfo(value)
    except Exception:
        return None
    return value


def parse_homework(data: dict) -> dict:
    subject = read_text(data, "subject", "Предмет", SUBJECT_MAX, required=True)
    description = read_text(data, "description", "Что задали", DESCRIPTION_MAX, required=True)
    raw_due = read_text(data, "dueDate", "Дата выполнения", 10, required=True)
    try:
        due = date.fromisoformat(raw_due)
    except ValueError:
        raise ApiError(400, "Укажите корректную дату выполнения")
    if not date(2020, 1, 1) <= due <= date(2100, 12, 31):
        raise ApiError(400, "Дата выполнения вне допустимого диапазона")
    return {
        "subject": subject,
        "description": description,
        "due_date": due.isoformat(),
        "pages": read_text(data, "pages", "Страница и упражнение", PAGES_MAX),
        "comment": read_text(data, "comment", "Комментарий", COMMENT_MAX),
    }


def detect_image(head: bytes) -> tuple[str, str] | None:
    """Определяет тип изображения по первым байтам файла (расширению не доверяем)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[\\/\x00-\x1f]", "_", name).strip()
    return cleaned[:120] or "photo"


def new_invite_code(conn) -> str:
    while True:
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(6))
        if conn.execute("SELECT 1 FROM classes WHERE invite_code = ?", (code,)).fetchone() is None:
            return code


def bump_version(class_id: int) -> None:
    """Меняет версию класса: по ней фронтенд понимает, что задания изменились."""
    g.db.execute("UPDATE classes SET version = version + 1 WHERE id = ?", (class_id,))


def remove_files(names) -> None:
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    for name in names:
        try:
            (upload_dir / name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            current_app.logger.warning("Не удалось удалить файл %s", name)


def forget_member_in_class(user_id: int, class_id: int) -> None:
    g.db.execute(
        """DELETE FROM completions WHERE user_id = ?
           AND homework_id IN (SELECT id FROM homework WHERE class_id = ?)""",
        (user_id, class_id),
    )
    g.db.execute(
        """DELETE FROM notifications WHERE user_id = ?
           AND homework_id IN (SELECT id FROM homework WHERE class_id = ?)""",
        (user_id, class_id),
    )


def load_user(uid: int):
    return g.db.execute(USER_SQL, (uid,)).fetchone()


def start_session(uid: int) -> None:
    session.clear()
    session.permanent = True
    session["uid"] = uid


def serialize_me(row) -> dict:
    cls = None
    if row["class_id"] is not None:
        cls = {"id": row["class_id"], "name": row["class_name"], "role": row["role"]}
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "timezone": row["timezone"],
        "reminderTime": row["reminder_time"],
        "remindDayBefore": bool(row["remind_day_before"]),
        "remindOnDay": bool(row["remind_on_day"]),
        "notifyNew": bool(row["notify_new"]),
        "class": cls,
    }


def is_admin() -> bool:
    return g.user["role"] == "admin"


def require_admin() -> None:
    if not is_admin():
        raise ApiError(403, "Это может сделать только администратор класса")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            raise ApiError(401, "Войдите в аккаунт")
        return view(*args, **kwargs)

    return wrapper


def class_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            raise ApiError(401, "Войдите в аккаунт")
        if g.user["class_id"] is None:
            raise ApiError(403, "Сначала создайте класс или вступите в него", code="no_class")
        return view(*args, **kwargs)

    return wrapper


def load_homework_row(hid: int):
    row = g.db.execute(
        "SELECT * FROM homework WHERE id = ? AND class_id = ?",
        (hid, g.user["class_id"]),
    ).fetchone()
    if row is None:
        raise ApiError(404, "Задание не найдено")
    return row


def can_edit_homework(row) -> bool:
    return is_admin() or row["author_id"] == g.user["id"]


def serialize_attachment(row, user) -> dict:
    return {
        "id": row["id"],
        "name": row["original_name"],
        "url": f"/api/attachments/{row['id']}",
        "canDelete": row["uploaded_by"] == user["id"] or user["role"] == "admin",
    }


def serialize_homework(row, attachments, user) -> dict:
    return {
        "id": row["id"],
        "subject": row["subject"],
        "description": row["description"],
        "dueDate": row["due_date"],
        "pages": row["pages"],
        "comment": row["comment"],
        "author": {"id": row["author_id"], "name": row["author_name"] or "Участник"},
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "done": row["completed_at"] is not None,
        "canEdit": row["author_id"] == user["id"] or user["role"] == "admin",
        "attachments": [serialize_attachment(a, user) for a in attachments],
    }


def fetch_homework(user, homework_id: int | None = None) -> list[dict]:
    where = "h.class_id = ?"
    params: list = [user["id"], user["class_id"]]
    att_where = "h.class_id = ?"
    att_params: list = [user["class_id"]]
    if homework_id is not None:
        where += " AND h.id = ?"
        params.append(homework_id)
        att_where += " AND a.homework_id = ?"
        att_params.append(homework_id)

    rows = g.db.execute(
        f"""SELECT h.*, u.display_name AS author_name, c.completed_at
            FROM homework h
            LEFT JOIN users u ON u.id = h.author_id
            LEFT JOIN completions c ON c.homework_id = h.id AND c.user_id = ?
            WHERE {where}
            ORDER BY h.due_date, h.id""",
        params,
    ).fetchall()
    att_rows = g.db.execute(
        f"""SELECT a.id, a.homework_id, a.original_name, a.uploaded_by
            FROM attachments a JOIN homework h ON h.id = a.homework_id
            WHERE {att_where} ORDER BY a.id""",
        att_params,
    ).fetchall()

    grouped: dict[int, list] = defaultdict(list)
    for att in att_rows:
        grouped[att["homework_id"]].append(att)
    return [serialize_homework(r, grouped.get(r["id"], []), user) for r in rows]


def class_payload() -> dict:
    cls = g.db.execute("SELECT * FROM classes WHERE id = ?", (g.user["class_id"],)).fetchone()
    members = g.db.execute(
        """SELECT u.id, u.display_name, u.username, m.role, m.joined_at
           FROM memberships m JOIN users u ON u.id = m.user_id
           WHERE m.class_id = ?
           ORDER BY (m.role = 'admin') DESC, m.joined_at, u.id""",
        (cls["id"],),
    ).fetchall()
    return {
        "id": cls["id"],
        "name": cls["name"],
        "inviteCode": cls["invite_code"],
        "version": cls["version"],
        "role": g.user["role"],
        "members": [
            {
                "id": m["id"],
                "displayName": m["display_name"],
                "username": m["username"],
                "role": m["role"],
                "joinedAt": m["joined_at"],
            }
            for m in members
        ],
    }


# ---------------------------------------------------------------- request hooks

@api_bp.before_request
def load_request_user() -> None:
    g.db = dbm.connect(current_app.config["DB_PATH"])
    g.user = None
    uid = session.get("uid")
    if uid is not None:
        g.user = load_user(uid)
        if g.user is None:
            session.clear()


@api_bp.teardown_request
def close_request_db(_exc) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@api_bp.errorhandler(ApiError)
def handle_api_error(err: ApiError):
    body = {"error": err.message}
    if err.code:
        body["code"] = err.code
    return jsonify(body), err.status


# ---------------------------------------------------------------- auth

@api_bp.post("/auth/register")
def register():
    data = read_json()
    username = read_username(data)
    display_name = read_text(data, "displayName", "Имя", NAME_MAX, required=True)
    password = read_password(data, "password")
    tz = read_timezone(data.get("timezone")) or "UTC"
    try:
        cur = g.db.execute(
            """INSERT INTO users (username, display_name, password_hash, timezone, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (username, display_name, generate_password_hash(password), tz, iso(now_utc())),
        )
    except sqlite3.IntegrityError:
        raise ApiError(409, "Такой логин уже занят")
    g.db.commit()
    start_session(cur.lastrowid)
    return jsonify(serialize_me(load_user(cur.lastrowid))), 201


@api_bp.post("/auth/login")
def login():
    data = read_json()
    username = read_text(data, "username", "Логин", 32, required=True).lower()
    password = data.get("password")
    if not isinstance(password, str):
        raise ApiError(400, "Введите пароль")
    limiter: AttemptLimiter = current_app.extensions["login_limiter"]
    key = f"{request.remote_addr or 'unknown'}:{username}"
    if limiter.blocked(key):
        raise ApiError(429, "Слишком много попыток входа. Попробуйте через 15 минут")

    row = g.db.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        limiter.hit(key)
        raise ApiError(401, "Неверный логин или пароль")

    limiter.reset(key)
    tz = read_timezone(data.get("timezone"))
    if tz:
        g.db.execute("UPDATE users SET timezone = ? WHERE id = ?", (tz, row["id"]))
        g.db.commit()
    start_session(row["id"])
    return jsonify(serialize_me(load_user(row["id"])))


@api_bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@api_bp.get("/me")
def me():
    if g.user is None:
        raise ApiError(401, "Войдите в аккаунт")
    return jsonify(serialize_me(g.user))


@api_bp.patch("/me")
@login_required
def update_me():
    data = read_json()
    updates: dict[str, object] = {}
    if "displayName" in data:
        updates["display_name"] = read_text(data, "displayName", "Имя", NAME_MAX, required=True)
    if "reminderTime" in data:
        value = data["reminderTime"]
        if not isinstance(value, str) or not TIME_RE.match(value):
            raise ApiError(400, "Укажите время напоминания в формате ЧЧ:ММ")
        updates["reminder_time"] = value
    for key, column in (
        ("remindDayBefore", "remind_day_before"),
        ("remindOnDay", "remind_on_day"),
        ("notifyNew", "notify_new"),
    ):
        if key in data:
            if not isinstance(data[key], bool):
                raise ApiError(400, "Настройка должна быть включена или выключена")
            updates[column] = int(data[key])
    if "timezone" in data:
        tz = read_timezone(data["timezone"])
        if tz is None:
            raise ApiError(400, "Некорректный часовой пояс")
        updates["timezone"] = tz

    if updates:
        # Имена столбцов берутся только из констант выше, поэтому подстановка безопасна.
        assignments = ", ".join(f"{column} = ?" for column in updates)
        g.db.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            [*updates.values(), g.user["id"]],
        )
        g.db.commit()
    return jsonify(serialize_me(load_user(g.user["id"])))


@api_bp.put("/me/password")
@login_required
def change_password():
    data = read_json()
    current = data.get("currentPassword")
    if not isinstance(current, str) or not check_password_hash(g.user["password_hash"], current):
        raise ApiError(400, "Текущий пароль введён неверно")
    new_password = read_password(data, "newPassword")
    g.db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), g.user["id"]),
    )
    g.db.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- classes

@api_bp.post("/classes")
@login_required
def create_class():
    if g.user["class_id"] is not None:
        raise ApiError(409, "Вы уже состоите в классе")
    data = read_json()
    name = read_text(data, "name", "Название класса", CLASS_NAME_MAX, required=True)
    now = iso(now_utc())
    code = new_invite_code(g.db)
    cur = g.db.execute(
        "INSERT INTO classes (name, invite_code, created_by, created_at) VALUES (?, ?, ?, ?)",
        (name, code, g.user["id"], now),
    )
    g.db.execute(
        "INSERT INTO memberships (user_id, class_id, role, joined_at) VALUES (?, ?, 'admin', ?)",
        (g.user["id"], cur.lastrowid, now),
    )
    g.db.commit()
    return jsonify(serialize_me(load_user(g.user["id"]))), 201


@api_bp.post("/classes/join")
@login_required
def join_class():
    if g.user["class_id"] is not None:
        raise ApiError(409, "Вы уже состоите в классе. Сначала выйдите из него")
    limiter: AttemptLimiter = current_app.extensions["join_limiter"]
    key = f"user:{g.user['id']}"
    if limiter.blocked(key):
        raise ApiError(429, "Слишком много попыток. Попробуйте позже")
    data = read_json()
    code = read_text(data, "code", "Код приглашения", 12, required=True)
    code = code.upper().replace(" ", "").replace("-", "")
    cls = g.db.execute("SELECT id FROM classes WHERE invite_code = ?", (code,)).fetchone()
    if cls is None:
        limiter.hit(key)
        raise ApiError(404, "Класс с таким кодом не найден")
    try:
        g.db.execute(
            "INSERT INTO memberships (user_id, class_id, role, joined_at) VALUES (?, ?, 'member', ?)",
            (g.user["id"], cls["id"], iso(now_utc())),
        )
    except sqlite3.IntegrityError:
        raise ApiError(409, "Вы уже состоите в классе")
    bump_version(cls["id"])
    g.db.commit()
    return jsonify(serialize_me(load_user(g.user["id"])))


@api_bp.get("/class")
@class_required
def get_class():
    return jsonify(class_payload())


@api_bp.patch("/class")
@class_required
def rename_class():
    require_admin()
    data = read_json()
    name = read_text(data, "name", "Название класса", CLASS_NAME_MAX, required=True)
    g.db.execute("UPDATE classes SET name = ? WHERE id = ?", (name, g.user["class_id"]))
    bump_version(g.user["class_id"])
    g.db.commit()
    return jsonify(class_payload())


@api_bp.post("/class/invite-code")
@class_required
def regenerate_code():
    require_admin()
    code = new_invite_code(g.db)
    g.db.execute("UPDATE classes SET invite_code = ? WHERE id = ?", (code, g.user["class_id"]))
    g.db.commit()
    return jsonify(inviteCode=code)


@api_bp.patch("/class/members/<int:user_id>")
@class_required
def change_member_role(user_id: int):
    require_admin()
    data = read_json()
    role = data.get("role")
    if role not in ("admin", "member"):
        raise ApiError(400, "Роль должна быть admin или member")
    target = g.db.execute(
        "SELECT role FROM memberships WHERE user_id = ? AND class_id = ?",
        (user_id, g.user["class_id"]),
    ).fetchone()
    if target is None:
        raise ApiError(404, "Участник не найден")
    if target["role"] == role:
        return jsonify(ok=True)
    if role == "member":
        admins = g.db.execute(
            "SELECT COUNT(*) FROM memberships WHERE class_id = ? AND role = 'admin'",
            (g.user["class_id"],),
        ).fetchone()[0]
        if admins <= 1:
            raise ApiError(400, "В классе должен остаться хотя бы один администратор")
    g.db.execute(
        "UPDATE memberships SET role = ? WHERE user_id = ? AND class_id = ?",
        (role, user_id, g.user["class_id"]),
    )
    bump_version(g.user["class_id"])
    g.db.commit()
    return jsonify(ok=True)


@api_bp.delete("/class/members/<int:user_id>")
@class_required
def remove_member(user_id: int):
    require_admin()
    if user_id == g.user["id"]:
        raise ApiError(400, "Чтобы выйти из класса, используйте кнопку «Выйти из класса»")
    exists = g.db.execute(
        "SELECT 1 FROM memberships WHERE user_id = ? AND class_id = ?",
        (user_id, g.user["class_id"]),
    ).fetchone()
    if exists is None:
        raise ApiError(404, "Участник не найден")
    g.db.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
    forget_member_in_class(user_id, g.user["class_id"])
    bump_version(g.user["class_id"])
    g.db.commit()
    return jsonify(ok=True)


@api_bp.post("/class/leave")
@class_required
def leave_class():
    class_id = g.user["class_id"]
    uid = g.user["id"]
    others = g.db.execute(
        "SELECT COUNT(*) FROM memberships WHERE class_id = ? AND user_id <> ?",
        (class_id, uid),
    ).fetchone()[0]
    removed_files: list[str] = []

    if others == 0:
        # Последний участник уходит: класс и все его задания удаляются.
        removed_files = [
            row["stored_name"]
            for row in g.db.execute(
                """SELECT a.stored_name FROM attachments a
                   JOIN homework h ON h.id = a.homework_id WHERE h.class_id = ?""",
                (class_id,),
            ).fetchall()
        ]
        g.db.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    else:
        if is_admin():
            other_admins = g.db.execute(
                """SELECT COUNT(*) FROM memberships
                   WHERE class_id = ? AND role = 'admin' AND user_id <> ?""",
                (class_id, uid),
            ).fetchone()[0]
            if other_admins == 0:
                # Администратор уходит: права переходят самому раннему участнику.
                g.db.execute(
                    """UPDATE memberships SET role = 'admin'
                       WHERE user_id = (
                           SELECT user_id FROM memberships
                           WHERE class_id = ? AND user_id <> ?
                           ORDER BY joined_at, user_id LIMIT 1)""",
                    (class_id, uid),
                )
        g.db.execute("DELETE FROM memberships WHERE user_id = ?", (uid,))
        forget_member_in_class(uid, class_id)
        bump_version(class_id)
    g.db.commit()
    remove_files(removed_files)
    return jsonify(ok=True)


# ---------------------------------------------------------------- homework

@api_bp.get("/homework")
@class_required
def list_homework():
    return jsonify(fetch_homework(g.user))


@api_bp.get("/homework/<int:hid>")
@class_required
def get_homework(hid: int):
    load_homework_row(hid)
    return jsonify(fetch_homework(g.user, hid)[0])


@api_bp.post("/homework")
@class_required
def create_homework():
    data = parse_homework(read_json())
    now = now_utc()
    cur = g.db.execute(
        """INSERT INTO homework
           (class_id, author_id, subject, description, due_date, pages, comment, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            g.user["class_id"],
            g.user["id"],
            data["subject"],
            data["description"],
            data["due_date"],
            data["pages"],
            data["comment"],
            iso(now),
            iso(now),
        ),
    )
    homework_id = cur.lastrowid
    created = new_homework_notifications(
        g.db,
        g.user["class_id"],
        homework_id,
        g.user["id"],
        g.user["display_name"],
        data["subject"],
        data["description"],
        data["due_date"],
        now,
    )
    bump_version(g.user["class_id"])
    g.db.commit()
    current_app.extensions["push"].send_async(created)
    return jsonify(fetch_homework(g.user, homework_id)[0]), 201


@api_bp.put("/homework/<int:hid>")
@class_required
def update_homework(hid: int):
    row = load_homework_row(hid)
    if not can_edit_homework(row):
        raise ApiError(403, "Редактировать может только автор или администратор")
    data = parse_homework(read_json())
    g.db.execute(
        """UPDATE homework SET subject = ?, description = ?, due_date = ?,
           pages = ?, comment = ?, updated_at = ? WHERE id = ?""",
        (
            data["subject"],
            data["description"],
            data["due_date"],
            data["pages"],
            data["comment"],
            iso(now_utc()),
            hid,
        ),
    )
    if row["due_date"] != data["due_date"]:
        # Срок изменился: напоминания пересоздадутся по новой дате.
        g.db.execute(
            "DELETE FROM notifications WHERE homework_id = ? AND kind IN ('day_before', 'due_today')",
            (hid,),
        )
    bump_version(g.user["class_id"])
    g.db.commit()
    return jsonify(fetch_homework(g.user, hid)[0])


@api_bp.delete("/homework/<int:hid>")
@class_required
def delete_homework(hid: int):
    row = load_homework_row(hid)
    if not can_edit_homework(row):
        raise ApiError(403, "Удалить может только автор или администратор")
    names = [
        a["stored_name"]
        for a in g.db.execute("SELECT stored_name FROM attachments WHERE homework_id = ?", (hid,)).fetchall()
    ]
    g.db.execute("DELETE FROM homework WHERE id = ?", (hid,))
    bump_version(g.user["class_id"])
    g.db.commit()
    remove_files(names)
    return jsonify(ok=True)


@api_bp.put("/homework/<int:hid>/done")
@class_required
def set_done(hid: int):
    load_homework_row(hid)
    done = read_json().get("done")
    if not isinstance(done, bool):
        raise ApiError(400, "Укажите done: true или false")
    if done:
        g.db.execute(
            "INSERT OR IGNORE INTO completions (user_id, homework_id, completed_at) VALUES (?, ?, ?)",
            (g.user["id"], hid, iso(now_utc())),
        )
    else:
        g.db.execute(
            "DELETE FROM completions WHERE user_id = ? AND homework_id = ?",
            (g.user["id"], hid),
        )
    g.db.commit()
    done_count = g.db.execute(
        "SELECT COUNT(*) FROM completions WHERE user_id = ?", (g.user["id"],)
    ).fetchone()[0]
    return jsonify(done=done, doneCount=done_count)


@api_bp.post("/homework/<int:hid>/attachments")
@class_required
def upload_attachment(hid: int):
    load_homework_row(hid)
    count = g.db.execute(
        "SELECT COUNT(*) FROM attachments WHERE homework_id = ?", (hid,)
    ).fetchone()[0]
    if count >= MAX_ATTACHMENTS:
        raise ApiError(400, f"Можно прикрепить не больше {MAX_ATTACHMENTS} фото")
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise ApiError(400, "Выберите файл")
    blob = uploaded.read(MAX_FILE_BYTES + 1)
    if len(blob) > MAX_FILE_BYTES:
        raise ApiError(413, "Файл больше 5 МБ")
    kind = detect_image(blob[:16])
    if kind is None:
        raise ApiError(400, "Можно загружать только изображения: JPG, PNG, GIF или WebP")
    mime, ext = kind

    stored = f"{uuid.uuid4().hex}{ext}"
    (Path(current_app.config["UPLOAD_DIR"]) / stored).write_bytes(blob)
    cur = g.db.execute(
        """INSERT INTO attachments
           (homework_id, stored_name, original_name, mime_type, size, uploaded_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (hid, stored, safe_name(uploaded.filename), mime, len(blob), g.user["id"], iso(now_utc())),
    )
    bump_version(g.user["class_id"])
    g.db.commit()
    row = g.db.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(serialize_attachment(row, g.user)), 201


def load_attachment_row(aid: int):
    row = g.db.execute(
        """SELECT a.*, h.class_id FROM attachments a
           JOIN homework h ON h.id = a.homework_id WHERE a.id = ?""",
        (aid,),
    ).fetchone()
    if row is None or row["class_id"] != g.user["class_id"]:
        raise ApiError(404, "Файл не найден")
    return row


@api_bp.get("/attachments/<int:aid>")
@class_required
def get_attachment(aid: int):
    row = load_attachment_row(aid)
    response = send_from_directory(
        Path(current_app.config["UPLOAD_DIR"]),
        row["stored_name"],
        mimetype=row["mime_type"],
        download_name=row["original_name"],
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@api_bp.delete("/attachments/<int:aid>")
@class_required
def delete_attachment(aid: int):
    row = load_attachment_row(aid)
    if row["uploaded_by"] != g.user["id"] and not is_admin():
        raise ApiError(403, "Удалить фото может тот, кто его загрузил, или администратор")
    g.db.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    bump_version(g.user["class_id"])
    g.db.commit()
    remove_files([row["stored_name"]])
    return jsonify(ok=True)


# ---------------------------------------------------------------- notifications and sync

def serialize_notification(row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "body": row["body"],
        "homeworkId": row["homework_id"],
        "createdAt": row["created_at"],
        "readAt": row["read_at"],
    }


@api_bp.get("/notifications")
@login_required
def list_notifications():
    created = run_reminders(g.db, now_utc(), user_id=g.user["id"])
    current_app.extensions["push"].send_async(created)
    rows = g.db.execute(
        """SELECT id, kind, title, body, homework_id, created_at, read_at
           FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 100""",
        (g.user["id"],),
    ).fetchall()
    unread = g.db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (g.user["id"],),
    ).fetchone()[0]
    return jsonify(items=[serialize_notification(r) for r in rows], unread=unread)


@api_bp.post("/notifications/read")
@login_required
def mark_read():
    data = read_json()
    now = iso(now_utc())
    if data.get("all") is True:
        g.db.execute(
            "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
            (now, g.user["id"]),
        )
    else:
        ids = data.get("ids")
        if not isinstance(ids, list) or len(ids) > 500 or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in ids
        ):
            raise ApiError(400, "Укажите список идентификаторов ids")
        if ids:
            marks = ",".join("?" for _ in ids)
            g.db.execute(
                f"""UPDATE notifications SET read_at = ?
                    WHERE user_id = ? AND read_at IS NULL AND id IN ({marks})""",
                [now, g.user["id"], *ids],
            )
    g.db.commit()
    return jsonify(ok=True)


@api_bp.get("/sync")
@login_required
def sync():
    """Лёгкий запрос, который страница вызывает каждые 15 секунд.

    Возвращает версии данных: если они изменились, страница перезагружает задания.
    Здесь же обновляется часовой пояс и проверяются напоминания.
    """
    tz = read_timezone(request.args.get("tz"))
    if tz and tz != g.user["timezone"]:
        g.db.execute("UPDATE users SET timezone = ? WHERE id = ?", (tz, g.user["id"]))
        g.db.commit()
    now = now_utc()
    created = run_reminders(g.db, now, user_id=g.user["id"])
    current_app.extensions["push"].send_async(created)

    class_version = 0
    if g.user["class_id"] is not None:
        class_version = g.db.execute(
            "SELECT version FROM classes WHERE id = ?", (g.user["class_id"],)
        ).fetchone()[0]
    unread = g.db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
        (g.user["id"],),
    ).fetchone()[0]
    done_count = g.db.execute(
        "SELECT COUNT(*) FROM completions WHERE user_id = ?", (g.user["id"],)
    ).fetchone()[0]
    return jsonify(classVersion=class_version, unread=unread, doneCount=done_count, serverTime=iso(now))


# ---------------------------------------------------------------- push

@api_bp.get("/push/config")
@login_required
def push_config():
    push: PushService = current_app.extensions["push"]
    return jsonify(enabled=push.enabled, publicKey=push.public_key)


@api_bp.post("/push/subscribe")
@login_required
def push_subscribe():
    data = read_json()
    endpoint = read_text(data, "endpoint", "Подписка", 2048, required=True)
    if not endpoint.startswith("https://"):
        raise ApiError(400, "Некорректная подписка push-уведомлений")
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not isinstance(p256dh, str) or not isinstance(auth, str) or not p256dh or not auth:
        raise ApiError(400, "Некорректные ключи подписки")
    g.db.execute(
        """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET
             user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth""",
        (g.user["id"], endpoint, p256dh[:200], auth[:200], iso(now_utc())),
    )
    g.db.commit()
    return jsonify(ok=True), 201


@api_bp.post("/push/unsubscribe")
@login_required
def push_unsubscribe():
    endpoint = read_text(read_json(), "endpoint", "Подписка", 2048, required=True)
    g.db.execute(
        "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
        (g.user["id"], endpoint),
    )
    g.db.commit()
    return jsonify(ok=True)


@api_bp.post("/push/test")
@login_required
def push_test():
    push: PushService = current_app.extensions["push"]
    if not push.enabled:
        raise ApiError(503, "Push-уведомления не настроены на сервере")
    count = g.db.execute(
        "SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (g.user["id"],)
    ).fetchone()[0]
    if count == 0:
        raise ApiError(400, "Сначала включите push-уведомления на этом устройстве")
    push.send_async(
        [{"user_id": g.user["id"], "homework_id": None, "title": "ClassMate", "body": "Уведомления работают!"}]
    )
    return jsonify(sent=count)


@api_bp.get("/health")
def health():
    return jsonify(ok=True)


# ---------------------------------------------------------------- app factory

def _load_or_create_secret(data_dir: Path) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "secret_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    os.chmod(path, 0o600)
    return key


def create_app(test_config: dict | None = None) -> Flask:
    overrides = dict(test_config or {})
    data_dir = Path(
        overrides.pop("DATA_DIR", None) or os.environ.get("CLASSMATE_DATA_DIR") or BASE_DIR / "data"
    )
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config.update(
        DATA_DIR=str(data_dir),
        DB_PATH=str(data_dir / "classmate.db"),
        UPLOAD_DIR=str(data_dir / "uploads"),
        VAPID_KEY_PATH=str(data_dir / "vapid_private.pem"),
        VAPID_SUBJECT=os.environ.get("CLASSMATE_VAPID_SUBJECT", "mailto:admin@example.com"),
        SECRET_KEY=overrides.pop("SECRET_KEY", None)
        or os.environ.get("CLASSMATE_SECRET_KEY")
        or _load_or_create_secret(data_dir),
        SESSION_COOKIE_NAME="classmate_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CLASSMATE_SECURE_COOKIES") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=MAX_FILE_BYTES + 512 * 1024,
        SEND_FILE_MAX_AGE_DEFAULT=0,
        START_SCHEDULER=os.environ.get("CLASSMATE_DISABLE_SCHEDULER") != "1",
        CLOCK=None,
    )
    app.config.update(overrides)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    dbm.init_db(app.config["DB_PATH"])

    def clock() -> datetime:
        custom = app.config.get("CLOCK")
        return custom() if custom else datetime.now(timezone.utc)

    push = PushService(app.config["DB_PATH"], app.config["VAPID_KEY_PATH"], app.config["VAPID_SUBJECT"])
    app.extensions.update(
        clock=clock,
        push=push,
        login_limiter=AttemptLimiter(limit=10, window=15 * 60),
        join_limiter=AttemptLimiter(limit=20, window=15 * 60),
    )
    if app.config["START_SCHEDULER"]:
        ReminderScheduler(app.config["DB_PATH"], push, clock).start()

    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        response = send_from_directory(STATIC_DIR, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/sw.js")
    def service_worker():
        # Сервис-воркер должен управлять всем сайтом, поэтому он отдаётся из корня.
        response = send_from_directory(STATIC_DIR, "sw.js")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=HTTP_MESSAGES.get(err.code, err.description)), err.code
        return err

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        app.logger.exception("Внутренняя ошибка: %s", err)
        if request.path.startswith("/api/"):
            return jsonify(error="Внутренняя ошибка сервера"), 500
        return "Внутренняя ошибка сервера", 500

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    return app


_app_instance: Flask | None = None


def __getattr__(name: str):
    """Ленивое создание приложения для `gunicorn app:app` (тесты импортируют только create_app)."""
    global _app_instance
    if name == "app":
        if _app_instance is None:
            _app_instance = create_app()
        return _app_instance
    raise AttributeError(name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port, debug=False, threaded=True)
