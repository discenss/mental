"""Слой D — интейк-роутер входной самооценки (§12).

30 ответов (0–4) → баллы по 10 направлениям (0–12) → ранжирование
→ ведущий маршрут + 2 доп. фокуса → сборка клиентского текста. Баллы скрыты.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.services import i18n


def _config(db: Session) -> m.IntakeConfig:
    cfg = db.get(m.IntakeConfig, 1)
    if cfg is None:
        raise ValueError("intake не загружен")
    return cfg


def score_intake(db: Session, answers: dict[int, int], *, user_id: int | None = None,
                 persist: bool = True) -> dict:
    """answers: {номер_вопроса(1..30): значение(0..4)}.

    Маршрутизация (scores/leading/focus1/focus2/is_soft) считается только по базовым данным
    (direction.questions/tie_priority/soft_threshold) — перевод затрагивает только тексты,
    которые видит пользователь."""
    cfg = _config(db)
    language = i18n.resolve_language(db.get(m.User, user_id)) if user_id is not None else i18n.DEFAULT_LANGUAGE
    directions = db.execute(select(m.IntakeDirection)).scalars().all()

    # валидация ответов
    for n, v in answers.items():
        if not (0 <= v <= 4):
            raise ValueError(f"вопрос {n}: значение {v} вне 0..4")

    scores = {d.code: sum(answers.get(n, 0) for n in d.questions) for d in directions}

    # приоритет бережности → индекс в tie_priority (меньше = раньше)
    prio = {code: i for i, code in enumerate(cfg.tie_priority)}
    ranked = sorted(directions, key=lambda d: (-scores[d.code], prio.get(d.code, 99)))
    ordered = [d.code for d in ranked]

    leading, focus1, focus2 = ordered[0], ordered[1], ordered[2]
    is_soft = scores[leading] < cfg.soft_threshold

    # тексты интерпретаций (локализованные)
    def interp(code: str, slot: str) -> str:
        row = db.execute(
            select(m.IntakeInterp).where(m.IntakeInterp.direction_code == code,
                                         m.IntakeInterp.slot == slot)
        ).scalar_one_or_none()
        if row is None:
            return ""
        return i18n.overlay(db, m.IntakeInterpTranslation, m.IntakeInterpTranslation.interp_id,
                            row.id, language, row, ["client_text"])["client_text"]

    static = {}
    for t in db.execute(select(m.IntakeStaticText)).scalars().all():
        static[t.key] = i18n.overlay(db, m.IntakeStaticTextTranslation, m.IntakeStaticTextTranslation.static_key,
                                     t.key, language, t, ["text"])["text"]

    cfg_view = i18n.overlay(db, m.IntakeConfigTranslation, m.IntakeConfigTranslation.config_id,
                            cfg.id, language, cfg, ["soft_no_leading", "must_include"])

    parts = [static.get("pre_result", "")]
    if is_soft:
        parts.append(cfg_view["soft_no_leading"])
    parts.append(interp(leading, "leading"))
    parts.append(interp(focus1, "focus1"))
    parts.append(interp(focus2, "focus2"))
    parts.append(static.get("outro", ""))
    result_text = "\n\n".join(p for p in parts if p)

    leading_dir = next(d for d in directions if d.code == leading)
    leading_dir_view = i18n.overlay(db, m.IntakeDirectionTranslation, m.IntakeDirectionTranslation.direction_code,
                                    leading_dir.code, language, leading_dir, ["name_leading"])

    def _module_name(mod: m.Module) -> str:
        return i18n.overlay(db, m.ModuleTranslation, m.ModuleTranslation.module_code,
                            mod.code, language, mod, ["name"])["name"]

    # реальное имя модуля (может отличаться от имени направления); None — модуль ещё не готов
    leading_module_name = None
    if leading_dir.module_code:
        mod = db.get(m.Module, leading_dir.module_code)
        leading_module_name = _module_name(mod) if mod else None

    # какие модули вообще доступны сейчас (чтобы клиент никогда не упирался в тупик)
    dir_by_module = {d.module_code: d for d in directions if d.module_code}
    available_modules = [
        {"code": mod.code, "name": _module_name(mod),
         "is_leading": mod.code == leading_dir.module_code,
         "is_focus": dir_by_module.get(mod.code) is not None
                     and dir_by_module[mod.code].code in (focus1, focus2)}
        for mod in db.execute(select(m.Module)).scalars().all()
    ]

    if persist and user_id is not None:
        db.add(m.IntakeResult(
            user_id=user_id, scores=scores, leading=leading, focus1=focus1,
            focus2=focus2, is_soft=is_soft, chosen_module_code=None,
        ))
        db.commit()

    return {
        "leading": leading, "focus1": focus1, "focus2": focus2,
        "is_soft": is_soft,
        "leading_module": leading_dir.module_code,     # None для будущих направлений
        "leading_name": leading_dir_view["name_leading"],  # имя направления (интерпретация)
        "leading_module_name": leading_module_name,     # имя готового модуля (для кнопки) или None
        "available_modules": available_modules,         # что можно начать прямо сейчас
        "result_text": result_text,
        "must_include": cfg_view["must_include"],
        "_scores": scores,                             # скрыто от пользователя (для аналитики/тестов)
    }
