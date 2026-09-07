"""Тесты авторизации iOS и того, что бот НЕ сломан.

Главное, что проверяется: запросы без токена ведут себя как раньше (это бот),
а запросы с токеном опознаются по токену и не видят чужого (это приложение).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import auth as auth_svc

client = TestClient(app)

SECRET = "test-secret-for-tests"


@pytest.fixture(autouse=True)
def _enable_auth(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    yield


def _token(user_id: int, *, ttl_days: int = 1) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": str(user_id), "iat": int(now.timestamp()),
                       "exp": int((now + timedelta(days=ttl_days)).timestamp())},
                      SECRET, algorithm="HS256")


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def _make_user(provider: str, pid: str) -> int:
    r = client.post("/api/v1/users/resolve",
                    json={"provider": provider, "provider_user_id": pid})
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


# ── сессия ───────────────────────────────────────────────────────────────────

def test_me_requires_token():
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_profile():
    uid = _make_user("ios", "apple-sub-me")
    r = client.get("/api/v1/auth/me", headers=_auth(uid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == uid
    assert "ios" in body["providers"]


def test_expired_token_is_401_not_anonymous():
    """Истёкшая сессия должна давать явный 401, а не молча становиться анонимной."""
    uid = _make_user("ios", "apple-sub-exp")
    now = datetime.now(UTC)
    stale = jwt.encode({"sub": str(uid), "iat": int((now - timedelta(days=2)).timestamp()),
                        "exp": int((now - timedelta(days=1)).timestamp())},
                       SECRET, algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {stale}"})
    assert r.status_code == 401


def test_garbage_token_is_401():
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_auth_disabled_gives_503(monkeypatch):
    """Без JWT_SECRET вход отвечает 503, а не 500."""
    monkeypatch.setattr(settings, "jwt_secret", "")
    r = client.post("/api/v1/auth/apple", json={"identity_token": "x"})
    assert r.status_code in (401, 503)


def test_apple_requires_identity_token():
    assert client.post("/api/v1/auth/apple", json={}).status_code == 422


# ── ключевое: токен перебивает тело ──────────────────────────────────────────

def test_token_overrides_body_user_id():
    """`{"user_id": чужой}` не даёт авторизованному клиенту доступа к чужому аккаунту."""
    victim = _make_user("telegram", "victim-1")
    attacker = _make_user("ios", "attacker-1")
    r = client.post("/api/v1/journal", json={"user_id": victim, "text": "заметка"},
                    headers=_auth(attacker))
    assert r.status_code == 200, r.text
    # запись легла атакующему, а не жертве
    mine = client.post("/api/v1/journal/list", json={}, headers=_auth(attacker)).json()
    theirs = client.post("/api/v1/journal/list", json={"user_id": victim}).json()
    assert any(e["text"] == "заметка" for e in mine["entries"])
    assert not any(e["text"] == "заметка" for e in theirs["entries"])


def test_bot_still_works_without_token():
    """Регресс-тест на бота: тело запроса без токена по-прежнему опознаёт пользователя."""
    uid = _make_user("telegram", "bot-user-1")
    r = client.post("/api/v1/journal", json={"user_id": uid, "text": "из бота"})
    assert r.status_code == 200, r.text
    listed = client.post("/api/v1/journal/list", json={"user_id": uid}).json()
    assert any(e["text"] == "из бота" for e in listed["entries"])


# ── владение программой ──────────────────────────────────────────────────────

def test_enrollment_owner_check():
    """Чужой eid по угадыванию — 403 для авторизованного клиента."""
    owner = _make_user("ios", "owner-1")
    other = _make_user("ios", "other-1")
    r = client.post("/api/v1/enroll", json={"module_code": "BOUND"}, headers=_auth(owner))
    assert r.status_code == 200, r.text
    eid = r.json()["enrollment_id"]

    assert client.get(f"/api/v1/enrollments/{eid}/today", headers=_auth(owner)).status_code == 200
    assert client.get(f"/api/v1/enrollments/{eid}/today", headers=_auth(other)).status_code == 403
    # бот (без токена) — прежнее поведение, доступ есть
    assert client.get(f"/api/v1/enrollments/{eid}/today").status_code == 200


def test_single_active_route():
    """Одновременно только одна программа — как в боте."""
    uid = _make_user("ios", "single-route-1")
    assert client.post("/api/v1/enroll", json={"module_code": "BOUND"},
                       headers=_auth(uid)).status_code == 200
    # тот же маршрут повторно — идемпотентно, это не ошибка
    assert client.post("/api/v1/enroll", json={"module_code": "BOUND"},
                       headers=_auth(uid)).status_code == 200
    # другой маршрут поверх активного — отказ
    r = client.post("/api/v1/enroll", json={"module_code": "REAL"}, headers=_auth(uid))
    assert r.status_code == 409, r.text
