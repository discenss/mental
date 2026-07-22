"""Распознавание голоса через OpenAI Whisper (та же схема, что в rhythmos)."""
from __future__ import annotations

import html
import io
import logging

from aiogram import Bot
from aiogram.types import Message

from config import OPENAI_API_KEY, WHISPER_MODEL

logger = logging.getLogger(__name__)


async def transcribe_voice(bot: Bot, file_id: str, lang: str = "ru") -> str:
    """Скачать голосовое/аудио из Telegram и распознать через Whisper."""
    import openai
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY не задан — распознавание недоступно")

    tg_file = await bot.get_file(file_id)
    buf = io.BytesIO()
    await bot.download_file(tg_file.file_path, destination=buf)
    buf.seek(0)
    buf.name = "voice.ogg"

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    resp = await client.audio.transcriptions.create(
        model=WHISPER_MODEL, file=buf,
        language={"ru": "ru", "uk": "uk", "en": "en"}.get(lang),
        response_format="text",
    )
    text = resp.strip() if isinstance(resp, str) else str(resp).strip()
    logger.info("Whisper: %d символов (lang=%s)", len(text), lang)
    return text


async def message_text(msg: Message) -> str | None:
    """Текст сообщения: если голос/аудио — распознаём, иначе берём msg.text."""
    if msg.voice or msg.audio:
        file_id = (msg.voice or msg.audio).file_id
        try:
            text = await transcribe_voice(msg.bot, file_id)
        except Exception as e:                          # noqa: BLE001
            logger.warning("Не удалось распознать голос: %s", e)
            await msg.answer("Не получилось распознать голос. Можно ответить текстом.")
            return None
        if text and text.strip():
            # эхо распознанного — чтобы было видно, что голос принят
            await msg.answer(f"🎤 <i>{html.escape(text.strip())}</i>")
        else:
            await msg.answer("Голос не распознан (тишина?). Попробуйте ещё раз или ответьте текстом.")
            return None
        return text
    return msg.text
