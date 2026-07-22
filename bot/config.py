"""Настройки Telegram-бота Mental Club."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Грузим bot/.env (рядом с этим файлом), не перетирая уже заданные переменные окружения.
load_dotenv(Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PROVIDER = "telegram"

# ── Режим получения апдейтов ──────────────────────────────────────────────────
# Локально — polling (USE_WEBHOOK не задан). На сервере — webhook.
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "").lower() in ("1", "true", "yes")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "")           # напр. https://mental.rhythmos.online
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/tg/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")       # проверка X-Telegram-Bot-Api-Secret-Token
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8011"))  # порт aiohttp внутри контейнера

# Каталог аудио-практик (content/audio/). Бот и backend в одном репозитории:
# bot/ — сосед content/. Переопределяется AUDIO_DIR в .env, если бот вынесен отдельно.
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", str(Path(__file__).resolve().parent.parent / "content" / "audio")))

# Тот же ключ, что в backend (OPENAI_API_KEY) — для распознавания голоса (Whisper).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

# telegram_id тестировщиков, которым доступен тест-режим (перемотка). "*" — всем.
_raw = os.getenv("TESTER_IDS", "")
TESTER_IDS = {"*"} if _raw.strip() == "*" else {x.strip() for x in _raw.split(",") if x.strip()}


def is_tester(tg_id: int | str) -> bool:
    return "*" in TESTER_IDS or str(tg_id) in TESTER_IDS
