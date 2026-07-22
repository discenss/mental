"""Тестовый режим — быстрая перемотка модуля без дневного гейта.

Гейт «1 день/сутки» живёт в клиенте (боте); бэкенд time-agnostic. Здесь — прогон
день/неделя/программа с авто-ответами (пресеты) и дампом выдачи движка на каждом шаге.
Доступно только для enrollment.mode == 'test'.
"""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.services import progression, postmodule

PRESETS = {"best", "worst", "random"}


def _pick(options: list[dict], key: str, preset: str, rnd: random.Random) -> int:
    if preset == "random":
        return rnd.randrange(len(options))
    weights = [int(o.get(key, 0)) for o in options]
    target = max(weights) if preset == "best" else min(weights)
    return weights.index(target)


def auto_selfcheck(db: Session, module_code: str, week_n: int, preset: str,
                   rnd: random.Random) -> dict[int, int]:
    week = db.execute(select(m.ModuleWeek).where(m.ModuleWeek.module_code == module_code,
                                                 m.ModuleWeek.n == week_n)).scalar_one()
    qs = db.execute(select(m.SelfcheckQuestion).where(m.SelfcheckQuestion.week_id == week.id)
                    .order_by(m.SelfcheckQuestion.q_index)).scalars().all()
    out = {}
    for q in qs:
        key = "weight" if q.kind == "core" else "flag_weight"
        out[q.q_index] = _pick(q.options, key, preset, rnd)
    return out


def _auto_postmodule_answers(db: Session, module_code: str, preset: str,
                             rnd: random.Random) -> dict:
    cfg = db.get(m.PostmoduleConfig, module_code)
    if not cfg or cfg.kind != "test":
        return {}
    ans = {}
    for t in cfg.config["topics"]:
        picks = []
        for q in t["questions"]:
            picks.append(_pick(q["options"], "weight", preset, rnd))
        ans[t["tag"]] = picks
    return ans


def run(db: Session, enrollment: m.Enrollment, scope: str = "day",
        preset: str = "best", *, seed: int | None = None) -> dict:
    """scope: day | week | program. preset: best | worst | random.
    Возвращает транскрипт: что движок отдаёт на каждом шаге."""
    if enrollment.mode != "test":
        raise ValueError("перемотка доступна только в тестовом режиме (mode='test')")
    if preset not in PRESETS:
        raise ValueError(f"preset {preset} ∉ {PRESETS}")
    rnd = random.Random(seed)
    steps: list[dict] = []
    guard = 0

    while guard < 500:
        guard += 1
        t = progression.get_today(db, enrollment)
        if t["status"] == "completed":
            steps.append({"event": "module_completed"})
            break
        if t["status"] == "active":
            steps.append({
                "event": "day", "week": t["week"], "day": t["day"], "day_title": t["day_title"],
                "focus": t["focus"], "task": t["task"], "quiz": t["quiz"],
                "audio": t["audio"], "reflection": t["reflection"],
                "morning_markers": t["morning_markers"], "evening_markers": t["evening_markers"],
                "intent_questions": t.get("intent_questions") or [],
            })
            # авто-прогон не пишет рефлексии-заглушки: пустой список → дневник/ИИ-итог чисты
            progression.complete_day(db, enrollment, task_status="DONE",
                                     quiz_answer="(test)", reflection=[])
            if scope == "day":
                break
        elif t["status"] == "selfcheck_due":
            wk = t["week"]
            ans = auto_selfcheck(db, enrollment.module_code, wk, preset, rnd)
            res = progression.submit_selfcheck(db, enrollment, ans)
            steps.append({
                "event": "selfcheck", "week": wk, "preset": preset,
                "core_score": res["core_score"], "zone": res["zone"],
                "user_text": res["user_text"], "recommendation": res["recommendation"],
                "critical_texts": res["critical_texts"], "flags": res["flags"],
                "next": res["next"],
            })
            if scope in ("day", "week"):
                break

    result = {"scope": scope, "preset": preset, "steps": steps,
              "status": enrollment.status, "week": enrollment.current_week,
              "day": enrollment.current_day}

    # по завершении программы — постмодульная маршрутизация
    if enrollment.status == "completed" and scope == "program":
        pm = postmodule.run(db, enrollment, _auto_postmodule_answers(db, enrollment.module_code, preset, rnd))
        result["postmodule"] = pm
    return result
