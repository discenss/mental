"""Link-коды: склейка каналов в одного пользователя (Telegram/WhatsApp ↔ iOS).

Зачем: один человек, зашедший в бота и в приложение, иначе станет двумя разными
пользователями с двумя разными прогрессами. Канал, где личность уже известна (бот),
выдаёт короткий код; приложение предъявляет его вместе со своей сессией — и обе
identity сходятся на одном `users.id`.

Направление склейки: identity канала-источника переносится к пользователю приложения,
а прогресс (программы/дневник) — наоборот, забирается со стороны, где он есть. Так у
человека, который начал в боте и потом поставил приложение (типичный случай), ничего
не теряется.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m

CODE_TTL_MINUTES = 15


def _now() -> datetime:
    # naive UTC: остальные DateTime-колонки проекта тоже наивные (server_default=now())
    return datetime.now(UTC).replace(tzinfo=None)


def generate_code(db: Session, user_id: int, *, provider: str) -> dict:
    """Канал-источник просит код для своего пользователя. Прошлые коды гасим."""
    old = db.execute(
        select(m.LinkCode).where(m.LinkCode.user_id == user_id, m.LinkCode.used.is_(False))
    ).scalars().all()
    for c in old:
        c.used = True
    # 6 цифр: набирается вручную в приложении, поэтому коротко и без букв
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = _now() + timedelta(minutes=CODE_TTL_MINUTES)
    row = m.LinkCode(user_id=user_id, code=code, provider=provider, expires_at=expires)
    db.add(row)
    db.commit()
    return {"code": code, "expires_in_seconds": CODE_TTL_MINUTES * 60,
            "expires_at": expires.isoformat()}


def redeem_code(db: Session, *, app_user_id: int, code: str) -> dict:
    """Приложение предъявляет код. Возвращает итоговый user_id (после склейки)."""
    row = db.execute(
        select(m.LinkCode).where(m.LinkCode.code == str(code).strip(),
                                 m.LinkCode.used.is_(False))
    ).scalars().first()
    if row is None or row.expires_at < _now():
        raise ValueError("код неверный или истёк")

    source_user_id = row.user_id
    row.used = True
    if source_user_id == app_user_id:                       # уже один и тот же человек
        db.commit()
        return {"user_id": app_user_id, "merged": False, "moved": {}}

    moved = _merge_users(db, source_user_id=source_user_id, target_user_id=app_user_id)
    db.commit()
    return {"user_id": app_user_id, "merged": True, "moved": moved}


def _merge_users(db: Session, *, source_user_id: int, target_user_id: int) -> dict[str, int]:
    """Перенести identity и прогресс source → target, затем удалить source.

    Конфликт «у обоих есть активная программа» разрешаем в пользу target (пользователь
    сидит в приложении и видит именно её): программы источника переносим, но активные
    из них помечаем брошенными, чтобы не появилось два активных маршрута сразу.
    """
    moved: dict[str, int] = {}

    # identity источника переезжают к целевому пользователю (уникальность provider+id
    # сохраняется: строки не дублируются, а меняют владельца)
    idents = db.execute(
        select(m.UserIdentity).where(m.UserIdentity.user_id == source_user_id)
    ).scalars().all()
    for ident in idents:
        clash = db.execute(
            select(m.UserIdentity).where(m.UserIdentity.provider == ident.provider,
                                         m.UserIdentity.provider_user_id == ident.provider_user_id,
                                         m.UserIdentity.user_id == target_user_id)
        ).scalar_one_or_none()
        if clash is not None:                               # уже привязан — лишнюю удаляем
            db.delete(ident)
            continue
        ident.user_id = target_user_id
    moved["identities"] = len(idents)

    target_has_active = db.execute(
        select(m.Enrollment.id).where(m.Enrollment.user_id == target_user_id,
                                      m.Enrollment.status.in_(("active", "selfcheck_due")))
        .limit(1)
    ).scalar_one_or_none() is not None

    enrollments = db.execute(
        select(m.Enrollment).where(m.Enrollment.user_id == source_user_id)
    ).scalars().all()
    for e in enrollments:
        e.user_id = target_user_id
        if target_has_active and e.status in ("active", "selfcheck_due"):
            e.status = "abandoned"
    moved["enrollments"] = len(enrollments)

    for Model, label in ((m.JournalEntry, "journal_entries"),
                         (m.IntakeResult, "intake_results"),
                         (m.DeviceToken, "device_tokens")):
        rows = db.execute(select(Model).where(Model.user_id == source_user_id)).scalars().all()
        for r in rows:
            r.user_id = target_user_id
        moved[label] = len(rows)

    db.flush()
    source = db.get(m.User, source_user_id)
    if source is not None:
        db.delete(source)
    return moved
