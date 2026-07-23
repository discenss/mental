"""Разрешение аудио-практики в конкретный языковой вариант + кэш доставки по каналам.

Хранение файлов (диск сейчас, S3/R2 потом) абстрагировано через settings.audio_public_base_url:
пусто → публичного URL ещё нет (нет домена), канал должен читать файл локально с общего volume
(`content/audio/`); заполнено → отдаём готовый HTTPS URL, который любой канал (Telegram,
WhatsApp, будущие iOS/Android) может забрать напрямую. Смена диска на S3/R2/CDN позже — это
смена ОДНОЙ настройки, а не переписывание модели/загрузки контента.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings

DEFAULT_LANGUAGE = "ru"


def resolve(db: Session, code: str, language: str = DEFAULT_LANGUAGE) -> dict | None:
    """Найти аудио-практику `code` на языке `language`; при отсутствии — фолбэк на ru,
    затем на любой существующий язык (чтобы никогда не падать «нет такого языка»).
    Возвращает None, только если аудио с таким кодом вообще не существует."""
    asset = db.execute(select(m.AudioAsset).where(m.AudioAsset.code == code)).scalar_one_or_none()
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

    url = None
    if settings.audio_public_base_url:
        url = f"{settings.audio_public_base_url.rstrip('/')}/{code}/file?lang={variant.language}"
    return {
        "code": code, "title": asset.title,
        "language": variant.language, "requested_language": language, "fallback": fallback,
        "storage_key": variant.storage_key, "mime": variant.mime, "url": url,
        "cached": variant.channel_cache or {},
    }


def cache_delivery(db: Session, code: str, language: str, channel: str, ref: str) -> bool:
    """Запомнить ID доставки (Telegram file_id / WhatsApp media_id / …) для (code, language, канал).
    После этого повторные отправки того же варианта в тот же канал используют кэш, не гоняя файл."""
    asset = db.execute(select(m.AudioAsset).where(m.AudioAsset.code == code)).scalar_one_or_none()
    if not asset:
        return False
    variant = next((v for v in asset.variants if v.language == language), None)
    if not variant:
        return False
    cache = dict(variant.channel_cache or {})
    cache[channel] = ref
    variant.channel_cache = cache
    db.commit()
    return True
