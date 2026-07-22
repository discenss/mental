"""Постмодульная маршрутизация (§7.4) — два режима: test (REAL) и flags (BOUND).

Оба: автоперехода нет, только рекомендация; пользователь выбирает сам.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m


def _tag_to_module(db: Session) -> dict[str, str | None]:
    return {d.code: d.module_code for d in db.execute(select(m.IntakeDirection)).scalars().all()}


def _module_names(db: Session) -> dict[str, str]:
    """module_code → пользовательское имя модуля (для рекомендации смежного маршрута)."""
    return {mod.code: mod.name for mod in db.execute(select(m.Module)).scalars().all()}


def _tag_names(db: Session) -> dict[str, str]:
    """тег направления → короткое имя темы (для тем без готового модуля)."""
    return {d.code: d.name_short for d in db.execute(select(m.IntakeDirection)).scalars().all()}


def get_questions(db: Session, enrollment: m.Enrollment) -> dict:
    """Вопросы постмодуля для показа пользователю. Веса скрыты (§16).

    test (REAL): список тем, в каждой — вопросы с вариантами-текстами (21 вопрос).
    flags (BOUND): вопросов нет — маршрут собирается из накопленных flag-весов.
    """
    cfg = db.get(m.PostmoduleConfig, enrollment.module_code)
    if cfg is None or cfg.kind == "none":
        return {"kind": "none", "topics": []}
    if cfg.kind != "test":
        return {"kind": cfg.kind, "topics": []}          # flags — без вопросов
    topics = [
        {"tag": t["tag"], "name": t.get("name", t["tag"]),
         "questions": [{"question": q["question"],
                        "options": [o["text"] for o in q["options"]]}   # без weight
                       for q in t["questions"]]}
        for t in cfg.config["topics"]
    ]
    return {"kind": "test", "topics": topics}


def run_test(db: Session, enrollment: m.Enrollment, answers: dict[str, list[int]],
             *, persist: bool = True) -> dict:
    """REAL-режим. answers: {тег: [индексы вариантов по 3 вопросам темы]}. Балл темы 0..9."""
    cfg = db.get(m.PostmoduleConfig, enrollment.module_code)
    if cfg is None or cfg.kind != "test":
        raise ValueError("у модуля нет постмодульного теста")
    topics = cfg.config["topics"]
    priority = cfg.config.get("priority", [])
    prio = {t: i for i, t in enumerate(priority)}
    tag_mod = _tag_to_module(db)

    scores: dict[str, int] = {}
    for t in topics:
        tag = t["tag"]
        picks = answers.get(tag, [])
        s = 0
        for qi, q in enumerate(t["questions"]):
            if qi < len(picks) and 0 <= picks[qi] < len(q["options"]):
                s += int(q["options"][picks[qi]].get("weight", 0))
        scores[tag] = s

    # 6–9 заметно → рекомендовать; 3–5 умеренно → зона внимания; 0–2 → пропустить
    strong = sorted([t for t, s in scores.items() if s >= 6],
                    key=lambda t: (-scores[t], prio.get(t, 99)))
    attention = sorted([t for t, s in scores.items() if 3 <= s <= 5],
                       key=lambda t: (-scores[t], prio.get(t, 99)))
    names = _module_names(db)
    topic_name = {t["tag"]: t.get("name", t["tag"]) for t in topics}
    recommended = [{"tag": t, "score": scores[t], "module": tag_mod.get(t),
                    "module_name": names.get(tag_mod.get(t)), "topic_name": topic_name.get(t)}
                   for t in strong]

    if persist:
        db.add(m.PostmoduleResult(enrollment_id=enrollment.id, topic_scores=scores,
                                  recommended_modules=[r["module"] for r in recommended if r["module"]]))
        db.commit()
    return {"kind": "test", "scores": scores, "recommended": recommended,
            "attention": attention, "auto_switch": False}


def run_flags(db: Session, enrollment: m.Enrollment, *, persist: bool = True) -> dict:
    """BOUND-режим. Накопленные flag-веса из недель → до 2 смежных фокусов."""
    cfg = db.get(m.PostmoduleConfig, enrollment.module_code)
    if cfg is None or cfg.kind != "flags":
        raise ValueError("у модуля нет flags-постмодуля")
    texts = cfg.config.get("adjacent_focus_texts", {})
    accs = db.execute(
        select(m.FlagAccumulator).where(m.FlagAccumulator.enrollment_id == enrollment.id)
    ).scalars().all()

    # порог: вес 2 в ≥2 неделях ИЛИ суммарный ≥4
    qualified = [a for a in accs if a.weeks_hit >= 2 or a.total_weight >= 4]
    # приоритет: по числу недель, затем по весу
    qualified.sort(key=lambda a: (-a.weeks_hit, -a.total_weight))
    top = qualified[:2]                      # максимум 2 фокуса
    tag_mod = _tag_to_module(db)
    names = _module_names(db)
    tnames = _tag_names(db)

    focuses = [{"tag": a.tag, "total_weight": a.total_weight, "weeks_hit": a.weeks_hit,
                "text": texts.get(a.tag, ""), "module": tag_mod.get(a.tag),
                "module_name": names.get(tag_mod.get(a.tag)), "topic_name": tnames.get(a.tag)}
               for a in top]

    if persist:
        db.add(m.PostmoduleResult(enrollment_id=enrollment.id,
                                  topic_scores={a.tag: a.total_weight for a in accs},
                                  recommended_modules=[f["module"] for f in focuses if f["module"]]))
        db.commit()
    return {"kind": "flags", "focuses": focuses, "auto_switch": False}


def run(db: Session, enrollment: m.Enrollment, answers: dict | None = None) -> dict:
    cfg = db.get(m.PostmoduleConfig, enrollment.module_code)
    if cfg is None or cfg.kind == "none":
        return {"kind": "none"}
    if cfg.kind == "test":
        return run_test(db, enrollment, answers or {})
    return run_flags(db, enrollment)
