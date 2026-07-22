"""Тонкий identity-слой: multi-provider пользователь.

Общий `user` для всех каналов (telegram|ios|whatsapp). Каналы приносят свой
provider_user_id (telegram_id / apple sub / …), резолвер отдаёт единого User.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m

PROVIDERS = {"telegram", "ios", "whatsapp"}


def get_by_provider(db: Session, provider: str, provider_user_id: str | int) -> m.User | None:
    ident = db.execute(
        select(m.UserIdentity).where(m.UserIdentity.provider == provider,
                                     m.UserIdentity.provider_user_id == str(provider_user_id))
    ).scalar_one_or_none()
    return db.get(m.User, ident.user_id) if ident else None


def resolve_or_create(db: Session, provider: str, provider_user_id: str | int, *,
                      language: str = "ru", timezone: str | None = None) -> m.User:
    if provider not in PROVIDERS:
        raise ValueError(f"неизвестный provider: {provider}")
    user = get_by_provider(db, provider, provider_user_id)
    if user:
        return user
    user = m.User(preferred_language=language, timezone=timezone)
    db.add(user)
    db.flush()  # нужен user.id
    db.add(m.UserIdentity(user_id=user.id, provider=provider,
                          provider_user_id=str(provider_user_id)))
    db.commit()
    return user


def reset_user(db: Session, user_id: int) -> dict[str, int]:
    """Полный сброс данных прохождения: стираем все программы и записи пользователя.

    Сам User + UserIdentity остаются (пользователь не «разлогинивается»), обнуляется
    только прогресс: enrollments и все их дочерние строки, дневник, результаты интейка.
    """
    enr_ids = db.execute(
        select(m.Enrollment.id).where(m.Enrollment.user_id == user_id)
    ).scalars().all()
    counts: dict[str, int] = {}
    if enr_ids:
        for Model in (m.DailyEntry, m.SelfcheckResult, m.FlagAccumulator,
                      m.FinalProductInstance, m.PostmoduleResult):
            res = db.execute(Model.__table__.delete().where(Model.enrollment_id.in_(enr_ids)))
            counts[Model.__tablename__] = res.rowcount or 0
    for Model in (m.JournalEntry, m.IntakeResult):       # эти — по user_id
        res = db.execute(Model.__table__.delete().where(Model.user_id == user_id))
        counts[Model.__tablename__] = res.rowcount or 0
    res = db.execute(m.Enrollment.__table__.delete().where(m.Enrollment.user_id == user_id))
    counts["enrollments"] = res.rowcount or 0
    db.commit()
    return counts


def abandon_active_enrollment(db: Session, user_id: int) -> dict[str, int]:
    """Удалить ТЕКУЩУЮ незавершённую программу (active/selfcheck_due) и её данные.

    Завершённые (status='completed') программы и их записи в «Мой путь»/дневнике —
    сохраняются. Используется при «Сменить программу»: пользователь бросает текущий
    маршрут и выбирает новый, но история пройденного остаётся.
    """
    actives = db.execute(
        select(m.Enrollment).where(m.Enrollment.user_id == user_id,
                                   m.Enrollment.status.in_(("active", "selfcheck_due")))
    ).scalars().all()
    if not actives:
        return {"abandoned": 0}
    eids = [e.id for e in actives]
    codes = {e.module_code for e in actives}
    # module_code'ы, которые НЕ остаются завершёнными (чтобы не снести дневник пройденной
    # программы, если её код совпадает с брошенной — в норме коды разные)
    completed_codes = set(db.execute(
        select(m.Enrollment.module_code).where(m.Enrollment.user_id == user_id,
                                               m.Enrollment.status == "completed")
    ).scalars().all())
    counts: dict[str, int] = {}
    for Model in (m.DailyEntry, m.SelfcheckResult, m.FlagAccumulator,
                  m.FinalProductInstance, m.PostmoduleResult):
        res = db.execute(Model.__table__.delete().where(Model.enrollment_id.in_(eids)))
        counts[Model.__tablename__] = res.rowcount or 0
    # дневник брошенных программ — но не трогаем коды, у которых есть completed-запись
    drop_codes = [c for c in codes if c not in completed_codes]
    if drop_codes:
        res = db.execute(m.JournalEntry.__table__.delete().where(
            m.JournalEntry.user_id == user_id, m.JournalEntry.module_code.in_(drop_codes)))
        counts["journal_entries"] = res.rowcount or 0
    db.execute(m.Enrollment.__table__.delete().where(m.Enrollment.id.in_(eids)))
    counts["abandoned"] = len(eids)
    db.commit()
    return counts


def link_identity(db: Session, user: m.User, provider: str, provider_user_id: str | int) -> m.UserIdentity:
    """Привязать ещё один канал к существующему пользователю (Telegram ↔ iOS)."""
    if provider not in PROVIDERS:
        raise ValueError(f"неизвестный provider: {provider}")
    existing = get_by_provider(db, provider, provider_user_id)
    if existing and existing.id != user.id:
        raise ValueError("этот provider_user_id уже привязан к другому пользователю")
    ident = m.UserIdentity(user_id=user.id, provider=provider,
                           provider_user_id=str(provider_user_id))
    db.add(ident)
    db.commit()
    return ident
