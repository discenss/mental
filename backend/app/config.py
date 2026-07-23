"""Настройки backend Mental Club (pydantic Settings из окружения)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# .../mental/  (backend/app/config.py → parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = PROJECT_ROOT / "content"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # По умолчанию SQLite-файл в backend/ — для локальной проверки без Postgres.
    # В проде: postgresql+psycopg://user:pass@host/db
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'backend' / 'mental.db'}"
    content_dir: str = str(CONTENT_DIR)

    # ── аудио: публичный базовый URL для отдачи файлов (см. app.services.audio) ─
    # Пусто (по умолчанию) — публичного URL ещё нет (нет домена): каналы читают файл локально
    # с диска (общий volume). Как только есть домен — сюда, например,
    # "https://mental.rhythmos.online/api/v1/audio" (свой backend раздаёт сам, см. main.py) —
    # ничего в модели/загрузке контента менять не нужно. Позже для переезда на S3/R2/CDN —
    # меняется на URL бакета, тоже без изменений в коде/схеме (см. docs/DEPLOY.md об аудио).
    audio_public_base_url: str = ""

    # ── ИИ (та же схема, что в rhythmos): два тира моделей + провайдер ──────────
    llm_provider: str = "openai"                       # openai | anthropic
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # будни — простая/дешёвая модель (ask, лёгкий разбор текста)
    everyday_openai_model: str = "gpt-4o-mini"
    everyday_anthropic_model: str = "claude-3-5-haiku-20241022"
    # аналитика — более сильная модель (инсайты/итоги модуля)
    analytics_openai_model: str = "gpt-5.1"
    analytics_anthropic_model: str = "claude-sonnet-4-20250514"
    whisper_model: str = "whisper-1"                   # распознавание аудио
    llm_timeout: float = 30.0
    llm_max_retries: int = 2

    @property
    def llm_enabled(self) -> bool:
        key = self.openai_api_key if self.llm_provider == "openai" else self.anthropic_api_key
        return bool(key)


settings = Settings()
