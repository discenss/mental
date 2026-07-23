"""Day-progression engine (§7.1) — детерминированное линейное продвижение.

Модуль = 6 недель × 7 дней. День 7 → недельная самопроверка → следующая неделя.
Ничего не блокирует переход (§10). Статусы enrollment:
  active | selfcheck_due | completed
"""
from __future__ import annotations

from datetime import date as _date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.services import scoring, i18n


def _current_entry(db: Session, enrollment: m.Enrollment):
    return db.execute(
        select(m.DailyEntry).where(m.DailyEntry.enrollment_id == enrollment.id,
                                   m.DailyEntry.week_n == enrollment.current_week,
                                   m.DailyEntry.day_n == enrollment.current_day)
    ).scalar_one_or_none()


def _closed_today(db: Session, enrollment_id: int, day: _date) -> bool:
    """Закрыл ли пользователь какой-либо день (вечерняя сессия) в эту календарную дату."""
    return db.execute(
        select(m.DailyEntry.id).where(m.DailyEntry.enrollment_id == enrollment_id,
                                      m.DailyEntry.entry_date == day,
                                      m.DailyEntry.evening_done.is_(True)).limit(1)
    ).scalar_one_or_none() is not None


def enroll(db: Session, user_id: int, module_code: str, *, mode: str = "normal") -> m.Enrollment:
    module_code = module_code.upper()
    if db.get(m.Module, module_code) is None:
        raise ValueError(f"модуль {module_code} не найден")
    existing = db.execute(
        select(m.Enrollment).where(m.Enrollment.user_id == user_id,
                                   m.Enrollment.module_code == module_code,
                                   m.Enrollment.status != "completed",
                                   m.Enrollment.mode == mode)
    ).scalar_one_or_none()
    if existing:
        return existing
    e = m.Enrollment(user_id=user_id, module_code=module_code,
                     current_week=1, current_day=1, status="active", mode=mode)
    db.add(e)
    db.commit()
    return e


def _day(db: Session, module_code: str, week_n: int, day_n: int, language: str):
    """Возвращает (week, day, week_view, day_view) — *_view уже локализованы под `language`
    (ru — как есть, иначе — оверлей из ModuleWeekTranslation/ModuleDayTranslation)."""
    week = db.execute(
        select(m.ModuleWeek).where(m.ModuleWeek.module_code == module_code,
                                   m.ModuleWeek.n == week_n)
    ).scalar_one()
    day = db.execute(
        select(m.ModuleDay).where(m.ModuleDay.week_id == week.id,
                                  m.ModuleDay.day_n == day_n)
    ).scalar_one()
    week_view = i18n.overlay(db, m.ModuleWeekTranslation, m.ModuleWeekTranslation.week_id, week.id,
                            language, week,
                            ["title", "intro_screen", "meaning", "goal", "result",
                             "key_themes", "intent_questions"])
    day_view = i18n.overlay(db, m.ModuleDayTranslation, m.ModuleDayTranslation.day_id, day.id,
                            language, day,
                            ["title", "focus", "task_text", "task_subtasks", "quiz", "reflection"])
    return week, day, week_view, day_view


def get_today(db: Session, enrollment: m.Enrollment, *, today: _date | None = None) -> dict:
    if enrollment.status == "completed":
        return {"status": "completed"}
    if enrollment.status == "selfcheck_due":
        return {"status": "selfcheck_due", "week": enrollment.current_week}

    entry = _current_entry(db, enrollment)
    opened = entry is not None and entry.morning_done
    session = "evening" if opened else "morning"
    # гейт: открыть НОВЫЙ день нельзя, если сегодня уже закрыли день (вечернюю сессию)
    closed_today = _closed_today(db, enrollment.id, today) if today else False
    done_today = closed_today if session == "morning" else False

    language = i18n.resolve_language(enrollment.user)
    week, day, week_view, day_view = _day(db, enrollment.module_code, enrollment.current_week,
                                         enrollment.current_day, language)
    markers = db.execute(
        select(m.Marker).where(m.Marker.module_code == enrollment.module_code)
        .order_by(m.Marker.phase, m.Marker.idx)
    ).scalars().all()
    def _marker_view(x: m.Marker) -> dict:
        v = i18n.overlay(db, m.MarkerTranslation, m.MarkerTranslation.marker_id, x.id,
                         language, x, ["question", "options"])
        return {"idx": x.idx, "question": v["question"], "options": v["options"]}
    morning = [_marker_view(x) for x in markers if x.phase == "morning"]
    evening = [_marker_view(x) for x in markers if x.phase == "evening"]
    audio = db.execute(
        select(m.AudioAsset).where(m.AudioAsset.module_code == enrollment.module_code,
                                   m.AudioAsset.week_n == enrollment.current_week)
    ).scalars().all()
    # аудио дня по диапазону слота
    slot = {1: "A1", 2: "A1", 3: "A2", 4: "A2", 5: "A3", 6: "A3", 7: "FINAL"}[day.day_n]
    day_audio = next((a for a in audio if a.slot == slot), None)

    return {
        "status": "active", "done_today": done_today, "session": session,
        "week": enrollment.current_week, "day": day.day_n, "day_title": day_view["title"],
        "week_intro": {"title": week_view["title"], "intro_screen": week_view["intro_screen"],
                       "meaning": week_view["meaning"], "goal": week_view["goal"],
                       "result": week_view["result"], "key_themes": week_view["key_themes"]},
        "morning_markers": morning, "evening_markers": evening,
        "focus": day_view["focus"],
        "task": {"text": day_view["task_text"], "subtasks": day_view["task_subtasks"]},
        "quiz": day_view["quiz"],
        "reflection": day_view["reflection"],
        "intent_questions": week_view["intent_questions"],     # W6-спец
        # языко-независимо: код+заголовок практики. Доставку (файл/URL/кэш конкретного языка)
        # канал получает отдельным вызовом GET /audio/{code}/resolve?lang=… по требованию.
        "audio": {"code": day_audio.code, "title": day_audio.title}
                 if day_audio and day_audio.variants else None,
    }


def _sync_journal(db: Session, enrollment: m.Enrollment, week_n: int, day_n: int,
                  reflection: list, task_answer: str | None = None) -> None:
    """Ответ на задание + рефлексии дня → «Мой дневник» (§8, §12.1). Идемпотентно:
    перезаписываем записи этого дня.

    В дневник идут только свободные тексты пользователя: ответ на задание (task) и
    рефлексия (reflection). Маркеры, техстатус, квизы и самопроверка НЕ сохраняются.
    Пустые тексты не создают записей — поэтому авто-прогон тест-режима (пустые ответы)
    дневник не засоряет, а ручной прогон с реальными ответами — наполняет.
    """
    db.execute(
        m.JournalEntry.__table__.delete().where(
            m.JournalEntry.user_id == enrollment.user_id,
            m.JournalEntry.module_code == enrollment.module_code,
            m.JournalEntry.week_n == week_n, m.JournalEntry.day_n == day_n,
            m.JournalEntry.source_type.in_(("reflection", "task")),
        )
    )
    if isinstance(task_answer, str) and task_answer.strip():
        db.add(m.JournalEntry(
            user_id=enrollment.user_id, source_type="task",
            module_code=enrollment.module_code, week_n=week_n, day_n=day_n,
            text=task_answer.strip(),
        ))
    for text in reflection:
        if isinstance(text, str) and text.strip():
            db.add(m.JournalEntry(
                user_id=enrollment.user_id, source_type="reflection",
                module_code=enrollment.module_code, week_n=week_n, day_n=day_n,
                text=text.strip(),
            ))


def _get_or_create_entry(db: Session, enrollment: m.Enrollment):
    w, d = enrollment.current_week, enrollment.current_day
    entry = _current_entry(db, enrollment)
    if entry is None:
        entry = m.DailyEntry(enrollment_id=enrollment.id, week_n=w, day_n=d)
        db.add(entry)
    return entry, w, d


def _advance(enrollment: m.Enrollment, d: int) -> None:
    if d < 7:
        enrollment.current_day = d + 1
    else:
        enrollment.status = "selfcheck_due"   # день 7 пройден → пора самопроверке


def open_day(db: Session, enrollment: m.Enrollment, *, morning=None,
             entry_date: _date | None = None) -> dict:
    """Утренняя сессия: открыть день (маркеры + показ фокуса/задания). Без продвижения."""
    if enrollment.status != "active":
        raise ValueError(f"нельзя открыть день в статусе {enrollment.status}")
    entry, w, d = _get_or_create_entry(db, enrollment)
    entry.morning_answers = morning or {}
    entry.morning_done = True
    entry.entry_date = entry_date or _date.today()
    db.commit()
    return {"session": "evening", "week": w, "day": d}


def close_day(db: Session, enrollment: m.Enrollment, *, task_status=None, task_answer=None,
              quiz_answer=None, evening=None, reflection=None, entry_date: _date | None = None) -> dict:
    """Вечерняя сессия: статус задания + (опц.) ответ на задание + квиз + вечерние маркеры
    + рефлексия → продвижение."""
    if enrollment.status != "active":
        raise ValueError(f"нельзя закрыть день в статусе {enrollment.status}")
    entry, w, d = _get_or_create_entry(db, enrollment)
    if entry.entry_date is None:
        entry.entry_date = entry_date or _date.today()
    entry.morning_done = True
    entry.task_status = task_status
    entry.task_answer = task_answer
    entry.quiz_answer = quiz_answer
    entry.evening_answers = evening or {}
    entry.reflection_answers = reflection or []
    entry.evening_done = True
    _sync_journal(db, enrollment, w, d, reflection or [], task_answer=task_answer)
    _advance(enrollment, d)
    db.commit()
    return {"status": enrollment.status, "week": enrollment.current_week,
            "day": enrollment.current_day}


def complete_day(db: Session, enrollment: m.Enrollment, *, morning=None, task_status=None,
                 task_answer=None, quiz_answer=None, evening=None, reflection=None,
                 entry_date: _date | None = None) -> dict:
    """Весь день одним вызовом (тест-режим/авто-прогон): обе сессии сразу + продвижение."""
    if enrollment.status != "active":
        raise ValueError(f"нельзя завершить день в статусе {enrollment.status}")
    entry, w, d = _get_or_create_entry(db, enrollment)
    entry.morning_answers = morning or {}
    entry.task_status = task_status
    entry.task_answer = task_answer
    entry.quiz_answer = quiz_answer
    entry.evening_answers = evening or {}
    entry.reflection_answers = reflection or []
    entry.entry_date = entry_date or _date.today()
    entry.morning_done = True
    entry.evening_done = True
    _sync_journal(db, enrollment, w, d, reflection or [], task_answer=task_answer)
    _advance(enrollment, d)
    db.commit()
    return {"status": enrollment.status, "week": enrollment.current_week,
            "day": enrollment.current_day}


def submit_selfcheck(db: Session, enrollment: m.Enrollment, answers: dict[int, int]) -> dict:
    """Проводит самопроверку недели, затем открывает следующую неделю / завершает модуль."""
    if enrollment.status != "selfcheck_due":
        raise ValueError(f"самопроверка недоступна в статусе {enrollment.status}")
    week_n = enrollment.current_week
    result = scoring.score_week(db, enrollment, week_n, answers)

    if week_n < 6:
        enrollment.current_week = week_n + 1
        enrollment.current_day = 1
        enrollment.status = "active"          # следующая неделя открывается всегда (§10)
    else:
        enrollment.status = "completed"
    db.commit()

    result["next"] = {"status": enrollment.status, "week": enrollment.current_week}
    return result
