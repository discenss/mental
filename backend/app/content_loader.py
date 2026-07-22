"""Загрузка YAML-контента в БД: модули (content/modules/*.yaml) и интейк (content/intake.yaml).

Идемпотентно: перед загрузкой удаляет прежние строки того же модуля / весь интейк.
Валидация структуры — по нормативу §20 (см. check_module).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import models as m


# ── валидация модуля (норматив §6/§20) ───────────────────────────────────────

def check_module(data: dict) -> list[str]:
    issues: list[str] = []
    weeks = data.get("weeks", [])
    if len(weeks) != 6:
        issues.append(f"недель {len(weeks)} != 6")
    audio = data.get("audio_map", [])
    if len(audio) != 24:
        issues.append(f"аудио {len(audio)} != 24")
    markers = data.get("markers", {})
    for phase in ("morning", "evening"):
        if len(markers.get(phase, [])) != 5:
            issues.append(f"маркеры {phase} != 5")
    for w in weeks:
        n = w.get("n")
        days = w.get("days", [])
        if len(days) != 7:
            issues.append(f"W{n}: дней {len(days)} != 7")
        for d in days:
            if len(d.get("reflection", [])) != 3:
                issues.append(f"W{n}D{d.get('d')}: рефлексий != 3")
        sc = w.get("selfcheck", [])
        if len(sc) != 10:
            issues.append(f"W{n}: самопроверка {len(sc)} != 10")
        # зоны: покрытие [core_min, core_max] без разрывов
        core_min = sum(min(o.get("weight", 0) for o in q["options"]) for q in sc if q.get("kind") == "core")
        core_max = sum(max(o.get("weight", 0) for o in q["options"]) for q in sc if q.get("kind") == "core")
        zs = sorted(w.get("zones", []), key=lambda z: z["min"])
        if zs:
            if zs[0]["min"] != core_min or zs[-1]["max"] != core_max:
                issues.append(f"W{n}: зоны [{zs[0]['min']},{zs[-1]['max']}] != core [{core_min},{core_max}]")
            for i in range(1, len(zs)):
                if zs[i]["min"] != zs[i - 1]["max"] + 1:
                    issues.append(f"W{n}: разрыв/пересечение зон")
    return issues


# ── загрузка модуля ──────────────────────────────────────────────────────────

def load_module(db: Session, yaml_path: str | Path, *, validate: bool = True) -> str:
    data = yaml.safe_load(Path(yaml_path).read_text())
    mod = data["module"]
    code = mod["code"]

    if validate:
        issues = check_module(data)
        if issues:
            raise ValueError(f"Модуль {code} не прошёл валидацию:\n  - " + "\n  - ".join(issues))

    # снести прежние данные модуля через ORM-delete — он каскадит по relationship
    # на weeks→days/selfcheck/zones/criticals, markers, audio, final_product, postmodule.
    # (Core delete(Module) ORM-каскады НЕ запускает → дубли в дочерних таблицах.)
    existing = db.get(m.Module, code)
    if existing:
        # снять ссылки intake_directions.module_code на этот код перед удалением —
        # иначе FK-ограничение блокирует DELETE (Postgres проверяет строго, в отличие
        # от SQLite; на re-load после первого успешного запуска ссылка уже существует).
        # load_intake() всё равно позже пересоздаст все intake_directions с нуля.
        db.execute(update(m.IntakeDirection).where(m.IntakeDirection.module_code == code)
                  .values(module_code=None))
        db.delete(existing)
        db.flush()

    db.add(m.Module(
        code=code, name=mod["name"], subtitle=mod.get("subtitle"),
        content_version=mod["content_version"], final_product_kind=mod["final_product_kind"],
        postmodule_kind=mod["postmodule_kind"], passport=data.get("passport", {}),
    ))

    markers = data.get("markers", {})
    for phase in ("morning", "evening"):
        for mk in markers.get(phase, []):
            db.add(m.Marker(module_code=code, phase=phase, idx=mk["idx"],
                            question=mk["question"], options=mk["options"]))

    for a in data.get("audio_map", []):
        db.add(m.AudioAsset(
            module_code=code, week_n=a["week"], slot=a["slot"], code=a["code"],
            day_range=str(a.get("days") or a.get("day_range") or ""),
            title=a.get("title"), theme=a.get("theme"),
            media_filename=a.get("file"), mime=a.get("mime"),
            duration_sec=a.get("duration_sec"), size_bytes=a.get("size_bytes"),
        ))

    for w in data.get("weeks", []):
        week = m.ModuleWeek(
            module_code=code, n=w["n"], title=w["title"], intro_screen=w.get("intro_screen", ""),
            meaning=w.get("meaning", ""), goal=w.get("goal", ""), result=w.get("result", ""),
            key_themes=w.get("key_themes", []) or [], intent_questions=w.get("intent_questions", []) or [],
        )
        db.add(week)
        db.flush()  # нужен week.id

        for d in w.get("days", []):
            task = d.get("task", {}) or {}
            db.add(m.ModuleDay(
                week_id=week.id, day_n=d["d"], title=d.get("title", ""),
                focus=d.get("focus", ""), task_text=task.get("text", ""),
                task_subtasks=task.get("subtasks", []) or [], quiz=d.get("quiz", {}) or {},
                reflection=d.get("reflection", []) or [],
            ))
        for q in w.get("selfcheck", []):
            db.add(m.SelfcheckQuestion(
                week_id=week.id, q_index=q["q"], kind=q["kind"], tag=q.get("tag"),
                question=q["question"], options=q["options"],
            ))
        for z in w.get("zones", []):
            db.add(m.ZoneInterp(
                week_id=week.id, zone=z["zone"], score_min=z["min"], score_max=z["max"],
                sys_action=z.get("sys_action", ""), meaning=z.get("meaning", ""),
                user_text=z.get("user_text", ""), recommendation=z.get("recommendation", ""),
            ))
        for c in w.get("critical_triggers", []):
            db.add(m.CriticalTrigger(
                week_id=week.id, condition=c.get("condition", ""),
                options=c.get("options", []) or [], refs=c.get("refs", []) or [],
                min_hits=int(c.get("min_hits", 1)), additional_text=c.get("additional_text", ""),
            ))

    fp = data.get("final_product", {})
    if fp:
        db.add(m.FinalProductTemplate(module_code=code, title=fp.get("title", ""),
                                      sections=fp.get("sections", [])))
    pm = data.get("postmodule", {})
    if pm:
        cfg = {k: v for k, v in pm.items() if k != "kind"}
        db.add(m.PostmoduleConfig(module_code=code, kind=pm.get("kind", "none"), config=cfg))

    db.commit()
    return code


# ── загрузка интейка (§12) ────────────────────────────────────────────────────

def load_intake(db: Session, yaml_path: str | Path) -> int:
    data = yaml.safe_load(Path(yaml_path).read_text())
    intake = data["intake"]

    for tbl in (m.IntakeInterp, m.IntakeQuestion, m.IntakeDirection,
                m.IntakeStaticText, m.IntakeConfig):
        db.execute(delete(tbl))
    db.flush()

    db.add(m.IntakeConfig(
        id=1, version=intake["version"], client_intro=intake["client_intro"],
        start_button=intake["start_button"], reference_period=intake.get("reference_period", ""),
        answer_scale=intake["answer_scale"], thresholds=intake["thresholds"],
        soft_threshold=intake["soft_threshold"], soft_no_leading=intake["soft_no_leading"],
        tie_priority=intake["tie_priority"], no_show=intake.get("no_show", []),
        must_include=intake.get("must_include", ""),
    ))

    # направления привязываем к модулю, только если такой модуль уже загружен
    known = {c for (c,) in db.execute(select(m.Module.code)).all()}
    for d in data["directions"]:
        mc = (d.get("module") or "").upper() or None   # коды модулей — uppercase (§19)
        db.add(m.IntakeDirection(
            code=d["code"], name_short=d["name_short"], name_leading=d["name_leading"],
            purpose=d["purpose"], questions=d["questions"], tie_priority=d["tie_priority"],
            module_code=mc if mc in known else None,
        ))
    for q in data["questions"]:
        db.add(m.IntakeQuestion(n=q["n"], direction_code=q["direction"], text=q["text"]))

    interps = data["interpretations"]
    for slot in ("leading", "focus1", "focus2"):
        for dcode, text in interps[slot].items():
            db.add(m.IntakeInterp(direction_code=dcode, slot=slot, client_text=text))
    for key, text in interps["static"].items():
        db.add(m.IntakeStaticText(key=key, text=text))

    db.commit()
    return len(data["questions"])
