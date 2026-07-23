"""Мультиязычность контента (§ многоязычность): ru хранится в базовых таблицах контента как
есть, остальные языки — в сайдкар-таблицах `*Translation` (см. models.py). Один общий helper
для fallback: язык не ru и перевод есть → берём перевод; иначе — ru-значение из базовой строки.

Никогда не подменяет числовые/весовые поля (core_score, zone-границы, weight/flag_weight,
critical refs) — только текст, который видит пользователь.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m

SUPPORTED_LANGUAGES = ["ru", "en", "uk", "es", "de"]
DEFAULT_LANGUAGE = "ru"


def resolve_language(user: "m.User | None") -> str:
    lang = getattr(user, "preferred_language", None)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def overlay(db: Session, translation_model, fk_col, fk_val, language: str, base, fields: list[str]) -> dict:
    """{field: значение} для каждого поля из `fields`: перевод (если язык не ru, перевод
    существует и поле в нём непустое), иначе — значение из `base`."""
    out = {f: getattr(base, f) for f in fields}
    if language == DEFAULT_LANGUAGE or base is None:
        return out
    tr = db.execute(
        select(translation_model).where(fk_col == fk_val, translation_model.language == language)
    ).scalar_one_or_none()
    if tr is None:
        return out
    for f in fields:
        val = getattr(tr, f, None)
        if val:
            out[f] = val
    return out
