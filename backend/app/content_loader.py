"""Загрузка YAML-контента в БД: модули (content/modules/*.yaml) и интейк (content/intake.yaml).

Идемпотентно: перед загрузкой удаляет прежние строки того же модуля / весь интейк.
Валидация структуры — по нормативу §20 (см. check_module).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import delete, select
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


def _audio_variant_specs(a: dict):
    """Из записи audio_map достаёт (язык, {file, mime, duration_sec, size_bytes}) на каждый язык.

    Основной язык — `file`/`mime`/`duration_sec`/`size_bytes` на верхнем уровне записи,
    язык по умолчанию 'ru' (можно переопределить необязательным `language:`). Дополнительные
    языки — необязательный `files: {en: "AUDIO_..._en.mp3", uk: {file: "...", mime: "..."}}`
    (значение — либо просто имя файла, либо словарь с теми же полями, что у основного).
    Так контент можно вести на одном языке и добавлять переводы по мере готовности записей,
    не трогая уже загруженные (см. сохранение channel_cache в load_module).
    """
    primary_lang = a.get("language", "ru")
    if a.get("file"):
        yield primary_lang, {"file": a["file"], "mime": a.get("mime"),
                             "duration_sec": a.get("duration_sec"), "size_bytes": a.get("size_bytes")}
    for lang, spec in (a.get("files") or {}).items():
        if isinstance(spec, str):
            yield lang, {"file": spec}
        else:
            yield lang, {"file": spec.get("file"), "mime": spec.get("mime"),
                         "duration_sec": spec.get("duration_sec"), "size_bytes": spec.get("size_bytes")}


# ── загрузка модуля ──────────────────────────────────────────────────────────

def load_module(db: Session, yaml_path: str | Path, *, validate: bool = True) -> str:
    data = yaml.safe_load(Path(yaml_path).read_text())
    mod = data["module"]
    code = mod["code"]

    if validate:
        issues = check_module(data)
        if issues:
            raise ValueError(f"Модуль {code} не прошёл валидацию:\n  - " + "\n  - ".join(issues))

    # Идемпотентная перезагрузка: НЕ удаляем сам Module — на него ссылаются enrollments
    # (реальный прогресс пользователей) и intake_directions, и Postgres строго проверяет
    # эти FK при удалении (в отличие от SQLite, где такое молча проходит, пока не подставишь
    # реальные данные — здесь именно так и вскрылось: сначала на intake_directions, потом,
    # когда на сервере появились настоящие enrollments, на них тоже).
    # Вместо этого: сносим ТОЛЬКО дочерний контент (недели/дни/маркеры/аудио/…) через ORM-delete
    # (каскадит на day/selfcheck/zones/criticals и audio→variants), а сам Module обновляем
    # на месте — так enrollments/intake_directions/дневник ни на миг не остаются без родителя.
    existing = db.get(m.Module, code)
    # снимок кэша доставки аудио (tg_file_id и т.п.) по (код, язык) — перезагрузка контента
    # не должна каждый раз стирать уже накопленный кэш отправки в Telegram/WhatsApp.
    # Восстанавливаем только если storage_key не поменялся (иначе кэш будет указывать на
    # УЖЕ ДРУГОЙ файл — так неправильно).
    cache_snapshot: dict[tuple[str, str], tuple[str, dict]] = {}
    if existing:
        for asset in existing.audio:
            for v in asset.variants:
                cache_snapshot[(asset.code, v.language)] = (v.storage_key, v.channel_cache)
        for week in list(existing.weeks):
            db.delete(week)
        for mk in list(existing.markers):
            db.delete(mk)
        for a in list(existing.audio):
            db.delete(a)
        if existing.final_product:
            db.delete(existing.final_product)
        if existing.postmodule:
            db.delete(existing.postmodule)
        db.flush()
        existing.name = mod["name"]
        existing.subtitle = mod.get("subtitle")
        existing.content_version = mod["content_version"]
        existing.final_product_kind = mod["final_product_kind"]
        existing.postmodule_kind = mod["postmodule_kind"]
        existing.passport = data.get("passport", {})
    else:
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
        asset = m.AudioAsset(
            module_code=code, week_n=a["week"], slot=a["slot"], code=a["code"],
            day_range=str(a.get("days") or a.get("day_range") or ""),
            title=a.get("title"), theme=a.get("theme"),
        )
        db.add(asset)
        for lang, spec in _audio_variant_specs(a):
            storage_key = spec.get("file")
            if not storage_key:
                continue
            cached_key, cached_channels = cache_snapshot.get((a["code"], lang), (None, {}))
            channel_cache = cached_channels if cached_key == storage_key else {}
            asset.variants.append(m.AudioVariant(
                language=lang, storage_key=storage_key, mime=spec.get("mime"),
                duration_sec=spec.get("duration_sec"), size_bytes=spec.get("size_bytes"),
                channel_cache=channel_cache,
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


# ── переводы (§ многоязычность): ru — в базовых таблицах выше, остальные языки —
# в сайдкар-таблицах *Translation. Базовый контент должен быть уже загружен load_module/
# load_intake; сюда пишутся только строки перевода, сами ru-строки не трогаются.
# ─────────────────────────────────────────────────────────────────────────────

def check_translation(data: dict) -> list[str]:
    """Лёгкая структурная сверка перевода с оригиналом — те же счётчики, что в check_module,
    но терпимо к отсутствующим секциям (audio_map в переводах не нужен)."""
    issues: list[str] = []
    weeks = data.get("weeks", [])
    if weeks and len(weeks) != 6:
        issues.append(f"недель {len(weeks)} != 6")
    markers = data.get("markers", {})
    for phase in ("morning", "evening"):
        vals = markers.get(phase, [])
        if vals and len(vals) != 5:
            issues.append(f"маркеры {phase} != 5")
    for w in weeks:
        n = w.get("n")
        days = w.get("days", [])
        if days and len(days) != 7:
            issues.append(f"W{n}: дней {len(days)} != 7")
        for d in days:
            refl = d.get("reflection")
            if refl and len(refl) != 3:
                issues.append(f"W{n}D{d.get('d')}: рефлексий != 3")
        sc = w.get("selfcheck", [])
        if sc and len(sc) != 10:
            issues.append(f"W{n}: самопроверка {len(sc)} != 10")
    return issues


def _replace_translation(db: Session, model, language: str, fields: dict, **match) -> None:
    """Идемпотентно: удалить прежнюю строку перевода (match+language), вставить новую."""
    db.execute(delete(model).where(
        *[getattr(model, k) == v for k, v in match.items()], model.language == language))
    db.add(model(language=language, **match, **fields))


def load_module_translation(db: Session, yaml_path: str | Path, language: str | None = None,
                            *, validate: bool = True) -> str:
    """Перевод модуля: та же структура, что у основного real.yaml/bound.yaml, но только
    текстовые поля (числа/веса игнорируются). Базовый ru-модуль должен быть уже загружен."""
    data = yaml.safe_load(Path(yaml_path).read_text())
    mod = data["module"]
    code = mod["code"]
    language = language or data.get("language")
    if not language:
        raise ValueError(f"не указан язык перевода для {yaml_path}")
    if language == "ru":
        raise ValueError("для ru перевод не нужен — редактируйте основной YAML модуля")

    if validate:
        issues = check_translation(data)
        if issues:
            raise ValueError(f"Перевод {code}:{language} не прошёл валидацию:\n  - " + "\n  - ".join(issues))

    module = db.get(m.Module, code)
    if module is None:
        raise ValueError(f"модуль {code} ещё не загружен — сначала load_module (ru-файл)")

    _replace_translation(db, m.ModuleTranslation, language,
                        {"name": mod.get("name"), "subtitle": mod.get("subtitle"),
                         "passport": data.get("passport")},
                        module_code=code)

    markers = data.get("markers", {})
    for phase in ("morning", "evening"):
        for mk in markers.get(phase, []):
            marker = db.execute(
                select(m.Marker).where(m.Marker.module_code == code, m.Marker.phase == phase,
                                       m.Marker.idx == mk["idx"])
            ).scalar_one_or_none()
            if marker is None:
                continue
            _replace_translation(db, m.MarkerTranslation, language,
                                {"question": mk.get("question"), "options": mk.get("options")},
                                marker_id=marker.id)

    for w in data.get("weeks", []):
        week = db.execute(
            select(m.ModuleWeek).where(m.ModuleWeek.module_code == code, m.ModuleWeek.n == w["n"])
        ).scalar_one_or_none()
        if week is None:
            continue
        _replace_translation(db, m.ModuleWeekTranslation, language, {
            "title": w.get("title"), "intro_screen": w.get("intro_screen"),
            "meaning": w.get("meaning"), "goal": w.get("goal"), "result": w.get("result"),
            "key_themes": w.get("key_themes"), "intent_questions": w.get("intent_questions"),
        }, week_id=week.id)

        for d in w.get("days", []):
            day = db.execute(
                select(m.ModuleDay).where(m.ModuleDay.week_id == week.id, m.ModuleDay.day_n == d["d"])
            ).scalar_one_or_none()
            if day is None:
                continue
            task = d.get("task") or {}
            quiz = d.get("quiz") or {}
            _replace_translation(db, m.ModuleDayTranslation, language, {
                "title": d.get("title"), "focus": d.get("focus"),
                "task_text": task.get("text"), "task_subtasks": task.get("subtasks"),
                "quiz": {"question": quiz.get("question"), "options": quiz.get("options")} if quiz else None,
                "reflection": d.get("reflection"),
            }, day_id=day.id)

        for q in w.get("selfcheck", []):
            sq = db.execute(
                select(m.SelfcheckQuestion).where(m.SelfcheckQuestion.week_id == week.id,
                                                  m.SelfcheckQuestion.q_index == q["q"])
            ).scalar_one_or_none()
            if sq is None:
                continue
            option_texts = [o.get("text") for o in q["options"]] if q.get("options") else None
            _replace_translation(db, m.SelfcheckQuestionTranslation, language,
                                {"question": q.get("question"), "option_texts": option_texts},
                                question_id=sq.id)

        for z in w.get("zones", []):
            zi = db.execute(
                select(m.ZoneInterp).where(m.ZoneInterp.week_id == week.id, m.ZoneInterp.zone == z["zone"])
            ).scalar_one_or_none()
            if zi is None:
                continue
            _replace_translation(db, m.ZoneInterpTranslation, language, {
                "meaning": z.get("meaning"), "user_text": z.get("user_text"),
                "recommendation": z.get("recommendation"),
            }, zone_id=zi.id)

        # critical_triggers не имеют естественного ключа — сопоставляем по позиции в списке,
        # том же порядке, в котором load_module их вставлял для этой недели.
        triggers = db.execute(
            select(m.CriticalTrigger).where(m.CriticalTrigger.week_id == week.id)
            .order_by(m.CriticalTrigger.id)
        ).scalars().all()
        for t, ct in zip(w.get("critical_triggers", []), triggers):
            _replace_translation(db, m.CriticalTriggerTranslation, language,
                                {"additional_text": t.get("additional_text")}, trigger_id=ct.id)

    fp = data.get("final_product")
    if fp:
        _replace_translation(db, m.FinalProductTemplateTranslation, language,
                            {"title": fp.get("title"), "sections": fp.get("sections")},
                            module_code=code)

    pm = data.get("postmodule")
    if pm:
        cfg_text = {k: v for k, v in pm.items() if k != "kind"}
        _replace_translation(db, m.PostmoduleConfigTranslation, language,
                            {"config": cfg_text}, module_code=code)

    db.commit()
    return f"{code}:{language}"


def load_intake_translation(db: Session, yaml_path: str | Path, language: str | None = None) -> str:
    """Перевод интейка: та же структура, что у content/intake.yaml, только текст."""
    data = yaml.safe_load(Path(yaml_path).read_text())
    intake = data["intake"]
    language = language or data.get("language")
    if not language:
        raise ValueError(f"не указан язык перевода для {yaml_path}")
    if language == "ru":
        raise ValueError("для ru перевод не нужен — редактируйте content/intake.yaml")

    if db.get(m.IntakeConfig, 1) is None:
        raise ValueError("интейк ещё не загружен — сначала load_intake (ru-файл)")

    _replace_translation(db, m.IntakeConfigTranslation, language, {
        "client_intro": intake.get("client_intro"), "start_button": intake.get("start_button"),
        "reference_period": intake.get("reference_period"),
        "soft_no_leading": intake.get("soft_no_leading"), "must_include": intake.get("must_include"),
    }, config_id=1)

    for d in data.get("directions", []):
        if db.get(m.IntakeDirection, d["code"]) is None:
            continue
        _replace_translation(db, m.IntakeDirectionTranslation, language, {
            "name_short": d.get("name_short"), "name_leading": d.get("name_leading"),
            "purpose": d.get("purpose"),
        }, direction_code=d["code"])

    for q in data.get("questions", []):
        if db.get(m.IntakeQuestion, q["n"]) is None:
            continue
        _replace_translation(db, m.IntakeQuestionTranslation, language,
                            {"text": q.get("text")}, question_n=q["n"])

    interps = data.get("interpretations", {})
    for slot in ("leading", "focus1", "focus2"):
        for dcode, text in (interps.get(slot) or {}).items():
            interp = db.execute(
                select(m.IntakeInterp).where(m.IntakeInterp.direction_code == dcode,
                                             m.IntakeInterp.slot == slot)
            ).scalar_one_or_none()
            if interp is None:
                continue
            _replace_translation(db, m.IntakeInterpTranslation, language,
                                {"client_text": text}, interp_id=interp.id)

    for key, text in (interps.get("static") or {}).items():
        if db.get(m.IntakeStaticText, key) is None:
            continue
        _replace_translation(db, m.IntakeStaticTextTranslation, language,
                            {"text": text}, static_key=key)

    db.commit()
    return language


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
