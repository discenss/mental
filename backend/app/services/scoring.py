"""Scoring/zone engine + critical-answer logic (§7.2, §7.3).

Считает core_score (только kind==core), определяет зону, копит flag-веса по тегам,
срабатывает critical logic. Баллы пользователю не показываются (§16).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m


def _week(db: Session, module_code: str, week_n: int) -> m.ModuleWeek:
    w = db.execute(
        select(m.ModuleWeek).where(m.ModuleWeek.module_code == module_code,
                                   m.ModuleWeek.n == week_n)
    ).scalar_one_or_none()
    if w is None:
        raise ValueError(f"{module_code} W{week_n} не найдена")
    return w


def score_week(db: Session, enrollment: m.Enrollment, week_n: int,
               answers: dict[int, int], *, persist: bool = True) -> dict:
    """answers: {q_index(1..10): индекс_выбранного_варианта}."""
    week = _week(db, enrollment.module_code, week_n)
    questions = db.execute(
        select(m.SelfcheckQuestion).where(m.SelfcheckQuestion.week_id == week.id)
        .order_by(m.SelfcheckQuestion.q_index)
    ).scalars().all()

    core_score = 0
    flags: dict[str, int] = {}
    chosen_texts: list[str] = []
    chosen_idx: dict[int, int] = {}
    for q in questions:
        if q.q_index not in answers:
            continue
        oi = answers[q.q_index]
        if not (0 <= oi < len(q.options)):
            raise ValueError(f"W{week_n} Q{q.q_index}: вариант {oi} вне диапазона")
        chosen_idx[q.q_index] = oi
        opt = q.options[oi]
        chosen_texts.append(opt.get("text", ""))
        if q.kind == "core":
            core_score += int(opt.get("weight", 0))
        else:  # flag
            w = int(opt.get("flag_weight", 0))
            if w:
                flags[q.tag] = flags.get(q.tag, 0) + w

    # зона
    zones = db.execute(
        select(m.ZoneInterp).where(m.ZoneInterp.week_id == week.id)
    ).scalars().all()
    zone = next((z for z in zones if z.score_min <= core_score <= z.score_max), None)

    # critical-answer logic — по точным ссылкам refs {q,opt} (min_hits),
    # с fallback на устаревший матч по тексту варианта, если refs не заданы.
    triggers = db.execute(
        select(m.CriticalTrigger).where(m.CriticalTrigger.week_id == week.id)
    ).scalars().all()
    chosen_set = set(chosen_texts)

    def _fired(t: m.CriticalTrigger) -> bool:
        if t.refs:
            hits = sum(1 for r in t.refs if chosen_idx.get(r["q"]) == r["opt"])
            return hits >= (t.min_hits or 1)
        return bool(set(t.options) & chosen_set)   # fallback

    fired = [t for t in triggers if _fired(t)]
    critical_texts = [t.additional_text for t in fired]

    if persist:
        db.add(m.SelfcheckResult(
            enrollment_id=enrollment.id, week_n=week_n, core_score=core_score,
            zone=zone.zone if zone else "UNKNOWN",
            triggered_criticals=[t.condition for t in fired], flags=flags,
        ))
        # накопление флагов для flags-режима постмодуля (§7.4)
        for tag, w in flags.items():
            acc = db.execute(
                select(m.FlagAccumulator).where(m.FlagAccumulator.enrollment_id == enrollment.id,
                                                m.FlagAccumulator.tag == tag)
            ).scalar_one_or_none()
            if acc is None:
                acc = m.FlagAccumulator(enrollment_id=enrollment.id, tag=tag,
                                        total_weight=0, weeks_hit=0)
                db.add(acc)
            acc.total_weight += w
            if w >= 2:
                acc.weeks_hit += 1
        db.commit()

    return {
        "core_score": core_score,                       # скрыто от пользователя
        "zone": zone.zone if zone else None,
        "user_text": zone.user_text if zone else "",
        "recommendation": zone.recommendation if zone else "",
        "critical_texts": critical_texts,               # доп. мягкие блоки
        "flags": flags,                                 # скрыто
        "blocks_progression": False,                    # §10 — никогда не блокирует
    }
