import io
from datetime import datetime, timezone

from conftest import PNG


def add_homework(client, **overrides):
    payload = {"subject": "Математика", "description": "№ 145, 146", "dueDate": "2026-11-18"}
    payload.update(overrides)
    response = client.post("/api/homework", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def test_register_login_logout(app, make_user):
    client = make_user("vasya", "Вася")
    assert client.get("/api/me").get_json()["displayName"] == "Вася"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/me").status_code == 401

    duplicate = app.test_client().post(
        "/api/auth/register", json={"username": "VASYA", "displayName": "x", "password": "secret123"}
    )
    assert duplicate.status_code == 409

    bad = client.post("/api/auth/login", json={"username": "vasya", "password": "wrong!!"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"username": "Vasya", "password": "secret123"})
    assert good.status_code == 200
    assert client.get("/api/me").status_code == 200


def test_validation_errors(app, make_user):
    client = app.test_client()
    short = client.post("/api/auth/register", json={"username": "ab", "displayName": "x", "password": "secret123"})
    assert short.status_code == 400
    weak = client.post("/api/auth/register", json={"username": "abc", "displayName": "x", "password": "123"})
    assert weak.status_code == 400

    user = make_user("solo")
    assert user.get("/api/homework").get_json()["code"] == "no_class"
    user.post("/api/classes", json={"name": "5А"})
    assert user.post("/api/homework", json={"subject": "", "description": "x", "dueDate": "2026-11-18"}).status_code == 400
    assert user.post("/api/homework", json={"subject": "A", "description": "x", "dueDate": "18.11"}).status_code == 400
    assert user.patch("/api/me", json={"reminderTime": "25:00"}).status_code == 400


def test_login_rate_limit(app, make_user):
    make_user("target")
    client = app.test_client()
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "target", "password": "nope"})
    blocked = client.post("/api/auth/login", json={"username": "target", "password": "secret123"})
    assert blocked.status_code == 429


def test_homework_is_shared_with_the_whole_class(classroom):
    anya, petya, admin = classroom["anya"], classroom["petya"], classroom["admin"]
    created = add_homework(anya, pages="стр. 45", comment="Можно на листочке")

    for client in (petya, admin):
        items = client.get("/api/homework").get_json()
        assert [h["id"] for h in items] == [created["id"]]
        assert items[0]["author"]["name"] == "Аня"
        assert items[0]["pages"] == "стр. 45"

    assert petya.get("/api/homework").get_json()[0]["canEdit"] is False
    assert admin.get("/api/homework").get_json()[0]["canEdit"] is True


def test_edit_and_delete_permissions(classroom):
    anya, petya, admin = classroom["anya"], classroom["petya"], classroom["admin"]
    hw = add_homework(anya)
    url = f"/api/homework/{hw['id']}"
    update = {"subject": "Алгебра", "description": "№ 150", "dueDate": "2026-11-19"}

    assert petya.put(url, json=update).status_code == 403
    assert petya.delete(url).status_code == 403
    assert anya.put(url, json=update).get_json()["subject"] == "Алгебра"
    assert admin.put(url, json={**update, "description": "№ 151"}).status_code == 200

    hw2 = add_homework(petya)
    assert petya.delete(f"/api/homework/{hw2['id']}").status_code == 200
    assert admin.delete(url).status_code == 200
    assert anya.get("/api/homework").get_json() == []


def test_done_status_is_personal(classroom):
    anya, petya = classroom["anya"], classroom["petya"]
    hw = add_homework(anya)
    response = petya.put(f"/api/homework/{hw['id']}/done", json={"done": True})
    assert response.get_json() == {"done": True, "doneCount": 1}

    assert petya.get("/api/homework").get_json()[0]["done"] is True
    assert anya.get("/api/homework").get_json()[0]["done"] is False
    assert petya.get("/api/sync").get_json()["doneCount"] == 1

    petya.put(f"/api/homework/{hw['id']}/done", json={"done": False})
    assert petya.get("/api/homework").get_json()[0]["done"] is False


def test_other_class_cannot_see_homework(app, classroom, make_user):
    hw = add_homework(classroom["anya"])
    upload = classroom["anya"].post(
        f"/api/homework/{hw['id']}/attachments", data={"file": (io.BytesIO(PNG), "page.png")}
    )
    attachment_url = upload.get_json()["url"]

    stranger = make_user("stranger")
    stranger.post("/api/classes", json={"name": "11А"})
    assert stranger.get("/api/homework").get_json() == []
    assert stranger.get(f"/api/homework/{hw['id']}").status_code == 404
    assert stranger.put(f"/api/homework/{hw['id']}/done", json={"done": True}).status_code == 404
    assert stranger.get(attachment_url).status_code == 404


def test_attachments(classroom):
    anya, petya = classroom["anya"], classroom["petya"]
    hw = add_homework(anya)
    url = f"/api/homework/{hw['id']}/attachments"

    fake = petya.post(url, data={"file": (io.BytesIO(b"<script>alert(1)</script>"), "x.png")})
    assert fake.status_code == 400

    ok = petya.post(url, data={"file": (io.BytesIO(PNG), "доска.png")})
    assert ok.status_code == 201
    att = ok.get_json()
    image = anya.get(att["url"])
    assert image.status_code == 200
    assert image.mimetype == "image/png"
    assert image.headers["X-Content-Type-Options"] == "nosniff"
    assert image.data == PNG

    assert anya.delete(f"/api/attachments/{att['id']}").status_code == 403
    assert petya.delete(f"/api/attachments/{att['id']}").status_code == 200

    for _ in range(6):
        assert anya.post(url, data={"file": (io.BytesIO(PNG), "p.png")}).status_code == 201
    assert anya.post(url, data={"file": (io.BytesIO(PNG), "p.png")}).status_code == 400


def test_sync_version_changes_for_everyone(classroom):
    anya, petya = classroom["anya"], classroom["petya"]
    before = petya.get("/api/sync").get_json()["classVersion"]
    add_homework(anya)
    after = petya.get("/api/sync").get_json()["classVersion"]
    assert after > before


def test_new_homework_notifies_classmates_not_author(classroom):
    anya, petya, admin = classroom["anya"], classroom["petya"], classroom["admin"]
    hw = add_homework(anya, subject="История")

    assert anya.get("/api/notifications").get_json()["unread"] == 0
    data = petya.get("/api/notifications").get_json()
    assert data["unread"] == 1
    note = data["items"][0]
    assert note["kind"] == "new" and note["homeworkId"] == hw["id"]
    assert note["title"] == "Neue Aufgabe: История"

    petya.post("/api/notifications/read", json={"ids": [note["id"]]})
    assert petya.get("/api/sync").get_json()["unread"] == 0

    admin.patch("/api/me", json={"notifyNew": False})
    add_homework(anya)
    assert admin.get("/api/notifications").get_json()["unread"] == 1  # только первое задание
    admin.post("/api/notifications/read", json={"all": True})
    assert admin.get("/api/notifications").get_json()["unread"] == 0


def test_class_management(classroom, make_user):
    admin, anya, petya, code = classroom["admin"], classroom["anya"], classroom["petya"], classroom["code"]
    cls = admin.get("/api/class").get_json()
    assert [m["role"] for m in cls["members"]] == ["admin", "member", "member"]
    petya_id = next(m["id"] for m in cls["members"] if m["displayName"] == "Петя")

    assert anya.patch("/api/class", json={"name": "Взлом"}).status_code == 403
    assert admin.patch("/api/class", json={"name": "7Б класс"}).get_json()["name"] == "7Б класс"

    new_code = admin.post("/api/class/invite-code").get_json()["inviteCode"]
    assert new_code != code
    late = make_user("late")
    assert late.post("/api/classes/join", json={"code": code}).status_code == 404
    assert late.post("/api/classes/join", json={"code": new_code.lower()}).status_code == 200

    assert admin.delete(f"/api/class/members/{petya_id}").status_code == 200
    assert petya.get("/api/homework").status_code == 403

    # Последний администратор уходит: права передаются Ане (вступила раньше всех).
    assert admin.patch(f"/api/class/members/{cls['members'][0]['id']}", json={"role": "member"}).status_code == 400
    assert admin.post("/api/class/leave").status_code == 200
    assert anya.get("/api/me").get_json()["class"]["role"] == "admin"


def test_last_member_leaving_deletes_class(app, make_user):
    solo = make_user("solo")
    solo.post("/api/classes", json={"name": "1А"})
    hw = add_homework(solo)
    solo.post(f"/api/homework/{hw['id']}/attachments", data={"file": (io.BytesIO(PNG), "a.png")})
    assert solo.post("/api/class/leave").status_code == 200
    assert solo.get("/api/me").get_json()["class"] is None
    import os
    assert os.listdir(app.config["UPLOAD_DIR"]) == []


def test_push_subscription(classroom):
    anya = classroom["anya"]
    config = anya.get("/api/push/config").get_json()
    assert config["enabled"] is True and len(config["publicKey"]) > 80
    assert anya.post("/api/push/test").status_code == 400
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "key", "auth": "auth"}}
    assert anya.post("/api/push/subscribe", json={"endpoint": "http://bad", "keys": {}}).status_code == 400
    assert anya.post("/api/push/subscribe", json=sub).status_code == 201
    assert anya.post("/api/push/subscribe", json=sub).status_code == 201  # повтор не ломает
    assert anya.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]}).status_code == 200


def test_security_headers_and_static(app):
    client = app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert "ClassMate" in page.get_data(as_text=True)
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.get("/sw.js").headers["Service-Worker-Allowed"] == "/"
    assert client.get("/api/nope").get_json()["error"] == "Nicht gefunden"
