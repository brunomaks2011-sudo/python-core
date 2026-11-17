import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402


@pytest.fixture
def clock():
    """Управляемые «часы»: тест может перевести время вперёд."""
    return {"now": datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)}


@pytest.fixture
def app(tmp_path, clock):
    return create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "START_SCHEDULER": False,
            "SECRET_KEY": "test-secret",
            "CLOCK": lambda: clock["now"],
        }
    )


def register(app, username, name=None, tz="UTC"):
    client = app.test_client()
    response = client.post(
        "/api/auth/register",
        json={"username": username, "displayName": name or username, "password": "secret123", "timezone": tz},
    )
    assert response.status_code == 201, response.get_json()
    return client


@pytest.fixture
def make_user(app):
    return lambda username, name=None, tz="UTC": register(app, username, name, tz)


@pytest.fixture
def classroom(app, make_user):
    """Класс из администратора и двух учеников."""
    admin = make_user("admin", "Мария Ивановна")
    code = None
    response = admin.post("/api/classes", json={"name": "7Б"})
    assert response.status_code == 201
    code = admin.get("/api/class").get_json()["inviteCode"]
    anya = make_user("anya", "Аня")
    petya = make_user("petya", "Петя")
    for client in (anya, petya):
        assert client.post("/api/classes/join", json={"code": code}).status_code == 200
    return {"admin": admin, "anya": anya, "petya": petya, "code": code}


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
)
