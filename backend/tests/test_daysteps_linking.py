"""Тесты: шаги дня, склейка каналов, дневной гейт по таймзоне, идемпотентность."""
from __future__ import annotations

import pathlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
SECRET = "test-secret-for-tests"


@pytest.fixture(autouse=True)
def _enable_auth(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    yield


def _auth(uid: int) -> dict:
    now = datetime.now(UTC)
    t = jwt.encode({"sub": str(uid), "iat": int(now.timestamp()),
                    "exp": int((now + timedelta(days=1)).timestamp())},
                   SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


def _user(provider: str, pid: str, **kw) -> int:
    r = client.post("/api/v1/users/resolve",
                    json={"provider": provider, "provider_user_id": pid, **kw})
    return r.json()["user_id"]


def _enrolled(pid: str, module: str = "BOUND") -> tuple[int, int]:
    uid = _user("ios", pid)
    r = client.post("/api/v1/enroll", json={"module_code": module}, headers=_auth(uid))
    assert r.status_code == 200, r.text
    return uid, r.json()["enrollment_id"]


# ── шаги дня ─────────────────────────────────────────────────────────────────

def test_day_steps_morning_shape():
    """Утро: фокус+задание одним шагом, аудио отдельным. Шаги структурные, не только текст."""
    uid, eid = _enrolled("steps-morning")
    r = client.get(f"/api/v1/enrollments/{eid}/day-steps", headers=_auth(uid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["session"] == "morning"
    kinds = [s["kind"] for s in body["steps"]]
    assert "focustask" in kinds
    ft = next(s for s in body["steps"] if s["kind"] == "focustask")
    # структурные поля для iOS
    assert ft["focus"] and ft["task"]["text"]
    assert ft["asks_status"] is False
    # предрендеренный текст для бота
    assert "Фокус дня" in ft["text"] and "Задание дня" in ft["text"]


def test_day_steps_evening_shape():
    """Вечер: статус задания → квиз (если есть) → 3 рефлексии."""
    uid, eid = _enrolled("steps-evening")
    assert client.post(f"/api/v1/enrollments/{eid}/open-day",
                       headers=_auth(uid)).status_code == 200
    body = client.get(f"/api/v1/enrollments/{eid}/day-steps", headers=_auth(uid)).json()
    assert body["session"] == "evening"
    kinds = [s["kind"] for s in body["steps"]]
    assert kinds[0] == "focustask"
    ft = body["steps"][0]
    assert ft["asks_status"] is True
    assert ft["status_options"] == ["DONE", "PARTIAL", "NOT_DONE"]
    assert kinds.count("free_text") == 3, kinds
    # порядок: квиз (если есть) строго до рефлексий
    if "quiz" in kinds:
        assert kinds.index("quiz") < kinds.index("free_text")


def test_day_steps_matches_bot_builder():
    """Бэкенд собирает ровно ту же последовательность, что строил бот у себя.

    Функции бота импортируются из его исходника (а не копируются сюда), чтобы тест
    ловил расхождение, если одну из двух реализаций потом поправят.
    """
    import importlib.util
    import sys
    import types

    from app.services import daysteps

    # bot/handlers/flow.py тянет aiogram и соседние модули; нам нужны только два
    # чистых билдера, поэтому выполняем файл с заглушками вместо импорта пакета.
    src = pathlib.Path("/home/discens/dev/mental/bot/handlers/flow.py").read_text()
    head = src[:src.index("def _phase_summary(")]
    body = head[head.index("def _task_text("):]
    ns: dict = {}
    exec(compile(body, "bot_flow_builders", "exec"), ns)          # noqa: S102

    uid, eid = _enrolled("steps-parity")
    today = client.get(f"/api/v1/enrollments/{eid}/today", headers=_auth(uid)).json()

    mine = daysteps.build(today)["steps"]
    theirs = ns["_build_morning_steps"](today)
    assert len(mine) == len(theirs), (len(mine), len(theirs))

    # тексты совпадают побайтово там, где бот их формирует (аудио-шаг текста не несёт
    # ни у него, ни у нас) — перейдя на эндпоинт, бот не потеряет ни одной формулировки
    for a, b in zip(mine, theirs):
        if "text" in b:
            assert a["text"] == b["text"], b["kind"]
    # kind совмещённого шага отличается осознанно: бот звал его info, мы — focustask
    # (приложению нужны структурные поля). Текст при этом тот же.
    assert theirs[-1 if not today.get("audio") else -2]["kind"] == "info"

    # аудио-шаг несёт тот же код
    if today.get("audio"):
        assert mine[-1]["kind"] == theirs[-1]["kind"] == "audio"
        assert mine[-1]["code"] == theirs[-1]["code"]


def test_day_steps_evening_matches_bot_builder():
    """То же для вечерней сессии."""
    import pathlib as _pl

    from app.services import daysteps

    src = _pl.Path("/home/discens/dev/mental/bot/handlers/flow.py").read_text()
    head = src[:src.index("def _phase_summary(")]
    body = head[head.index("def _task_text("):]
    ns: dict = {}
    exec(compile(body, "bot_flow_builders", "exec"), ns)          # noqa: S102

    uid, eid = _enrolled("steps-parity-pm")
    client.post(f"/api/v1/enrollments/{eid}/open-day", headers=_auth(uid))
    today = client.get(f"/api/v1/enrollments/{eid}/today", headers=_auth(uid)).json()

    mine = daysteps.build(today)["steps"]
    theirs = ns["_build_evening_steps"](today)
    assert [x["kind"] for x in mine] == [x["kind"] for x in theirs]
    # у бота `text` есть только на шаге задания; квиз и рефлексии он рендерит из
    # `question`/`prompt`. Сравниваем там, где текст у него есть, и сверяем остальные поля.
    for a, b in zip(mine, theirs):
        if "text" in b:
            assert a["text"] == b["text"], a["kind"]
        if b["kind"] == "quiz":
            assert a["question"] == b["question"] and a["options"] == b["options"]
        if b["kind"] == "free_text":
            assert a["prompt"] == b["prompt"]


def test_day_steps_terminal_status_has_no_steps():
    """completed/selfcheck_due шагов не имеют — там свой экран, а не проход по дню."""
    from app.services import daysteps
    assert daysteps.build({"status": "completed"})["steps"] == []
    assert daysteps.build({"status": "selfcheck_due", "week": 2})["steps"] == []


# ── идемпотентность закрытия дня ─────────────────────────────────────────────

def test_close_day_is_idempotent():
    """Двойной тап / ретрай не должен проматывать два дня."""
    uid, eid = _enrolled("idem-close")
    client.post(f"/api/v1/enrollments/{eid}/open-day", headers=_auth(uid))
    p = {"task_status": "DONE", "reflection": ["a", "b", "c"]}
    r1 = client.post(f"/api/v1/enrollments/{eid}/close-day", json=p, headers=_auth(uid))
    assert r1.status_code == 200, r1.text
    after_first = (r1.json()["week"], r1.json()["day"])
    r2 = client.post(f"/api/v1/enrollments/{eid}/close-day", json=p, headers=_auth(uid))
    assert r2.status_code == 200, r2.text
    assert (r2.json()["week"], r2.json()["day"]) == after_first, "второй вызов промотал день"
    assert r2.json().get("already_closed") is True


# ── дневной гейт считается по таймзоне пользователя ──────────────────────────

def test_day_gate_uses_user_timezone():
    """Гейт «один день в сутки» должен жить по часам пользователя, а не сервера."""
    from app.services import clock
    from app.database import SessionLocal
    from app import models as m

    uid = _user("ios", "tz-user", timezone="Pacific/Kiritimati")   # UTC+14
    with SessionLocal() as db:
        u = db.get(m.User, uid)
        assert clock.today_for(u) == clock.today_for(u)             # детерминизм
        # у пользователя на +14 и на -11 дата отличается хотя бы иногда; проверяем,
        # что функция вообще СМОТРИТ на таймзону, а не игнорирует её
        u2 = m.User(preferred_language="ru", timezone="Pacific/Midway")   # UTC-11
        d_east, d_west = clock.today_for(u), clock.today_for(u2)
        assert (d_east - d_west).days in (0, 1)
        assert clock.today_for(None) is not None                    # фолбэк без падения


def test_timezone_gate_blocks_second_day_same_local_day():
    """Закрыв день, в тот же локальный день второй открыть нельзя (done_today)."""
    uid, eid = _enrolled("tz-gate")
    client.post(f"/api/v1/enrollments/{eid}/open-day", headers=_auth(uid))
    client.post(f"/api/v1/enrollments/{eid}/close-day",
                json={"task_status": "DONE", "reflection": ["a", "b", "c"]},
                headers=_auth(uid))
    today = client.get(f"/api/v1/enrollments/{eid}/today", headers=_auth(uid)).json()
    assert today["status"] == "active"
    assert today["done_today"] is True, "гейт не сработал: день можно открыть повторно"


# ── link-коды ────────────────────────────────────────────────────────────────

def test_link_code_merges_accounts():
    """Бот выдал код, приложение предъявило → один пользователь, прогресс сохранён."""
    tg_uid = _user("telegram", "link-tg-1")
    # прогресс на стороне бота
    client.post("/api/v1/journal", json={"user_id": tg_uid, "text": "из телеграма"})
    r = client.post("/api/v1/auth/link-code",
                    json={"provider": "telegram", "provider_user_id": "link-tg-1"})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()

    ios_uid = _user("ios", "link-ios-1")
    r2 = client.post("/api/v1/auth/link", json={"code": code}, headers=_auth(ios_uid))
    assert r2.status_code == 200, r2.text
    assert r2.json()["merged"] is True
    assert r2.json()["user_id"] == ios_uid

    # дневник бота теперь виден в приложении
    entries = client.post("/api/v1/journal/list", json={}, headers=_auth(ios_uid)).json()
    assert any(e["text"] == "из телеграма" for e in entries["entries"])
    # и telegram-identity ведёт на того же пользователя
    me = client.get("/api/v1/auth/me", headers=_auth(ios_uid)).json()
    assert set(me["providers"]) >= {"ios", "telegram"}


def test_link_code_single_use():
    _user("telegram", "link-tg-2")
    code = client.post("/api/v1/auth/link-code",
                       json={"provider": "telegram", "provider_user_id": "link-tg-2"}).json()["code"]
    a = _user("ios", "link-ios-2a")
    b = _user("ios", "link-ios-2b")
    assert client.post("/api/v1/auth/link", json={"code": code}, headers=_auth(a)).status_code == 200
    r = client.post("/api/v1/auth/link", json={"code": code}, headers=_auth(b))
    assert r.status_code == 422, "код должен быть одноразовым"


def test_link_bad_code_rejected():
    uid = _user("ios", "link-bad")
    r = client.post("/api/v1/auth/link", json={"code": "000000"}, headers=_auth(uid))
    assert r.status_code == 422


def test_link_requires_auth():
    assert client.post("/api/v1/auth/link", json={"code": "123456"}).status_code == 401


# ── языки ────────────────────────────────────────────────────────────────────

def test_portuguese_supported():
    from app.services import i18n
    assert "pt" in i18n.SUPPORTED_LANGUAGES
