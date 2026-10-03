"""Разрешение текстовой практики в конкретный языковой вариант.

Аналог app.services.audio, но проще: тело практики — обычный текст в БД (загружен из
content/modules/*.yaml, text_map), файла/URL/канального кэша нет — канал получает текст
целиком и показывает/отправляет его сам.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m

DEFAULT_LANGUAGE = "ru"


def resolve(db: Session, code: str, language: str = DEFAULT_LANGUAGE) -> dict | None:
    """Найти текстовую практику `code` на языке `language`; при отсутствии — фолбэк на ru,
    затем на любой существующий язык. Возвращает None, только если такого кода нет вообще."""
    asset = db.execute(select(m.TextAsset).where(m.TextAsset.code == code)).scalar_one_or_none()
    if not asset:
        return None
    by_lang = {v.language: v for v in asset.variants}
    if language in by_lang:
        variant, fallback = by_lang[language], False
    elif DEFAULT_LANGUAGE in by_lang:
        variant, fallback = by_lang[DEFAULT_LANGUAGE], True
    elif by_lang:
        variant, fallback = next(iter(by_lang.values())), True
    else:
        return None
    return {
        "code": code, "title": asset.title,
        "language": variant.language, "requested_language": language, "fallback": fallback,
        "body": variant.body,
    }
