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

    # ── Авторизация iOS-клиента (§3.1 RIDGE-IOS-PROMPT) ────────────────────────
    # Бот НЕ затронут: он продолжает ходить в API телом запроса без токена.
    # Здесь только то, что нужно публичному мобильному клиенту.
    jwt_secret: str = ""                               # HS256; пусто → /auth/* отдаёт 503
    jwt_algorithm: str = "HS256"
    jwt_ttl_days: int = 90                             # мобильная сессия живёт долго

    # Apple Sign-In: audience = bundle id приложения. Ключи Apple тянем из их JWKS.
    apple_bundle_ids: str = ""                         # csv: day.ridge.app,day.ridge.app.dev
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    apple_issuer: str = "https://appleid.apple.com"

    # Google Sign-In: допустимые audience (iOS client id, при желании — web client id).
    google_client_ids: str = ""                        # csv
    google_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"
    google_issuers: str = "https://accounts.google.com,accounts.google.com"

    # Сервисный токен для внутренних вызовов (планировщик и т.п.). Пока пусто —
    # поведение как раньше (бот ходит без токена). Заполнение включает проверку.
    internal_api_token: str = ""

    # ── APNs (пуши для iOS; у бота свои напоминания через Telegram) ────────────
    apns_key_path: str = ""                            # путь к .p8; пусто → отправка no-op
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_topic: str = "day.ridge.app"                  # = bundle id
    apns_use_sandbox: bool = True

    @property
    def apple_audiences(self) -> list[str]:
        return [x.strip() for x in self.apple_bundle_ids.split(",") if x.strip()]

    @property
    def google_audiences(self) -> list[str]:
        return [x.strip() for x in self.google_client_ids.split(",") if x.strip()]

    @property
    def google_allowed_issuers(self) -> list[str]:
        return [x.strip() for x in self.google_issuers.split(",") if x.strip()]

    @property
    def auth_enabled(self) -> bool:
        return bool(self.jwt_secret)

    @property
    def apns_enabled(self) -> bool:
        return bool(self.apns_key_path and self.apns_key_id and self.apns_team_id)

    @property
    def llm_enabled(self) -> bool:
        key = self.openai_api_key if self.llm_provider == "openai" else self.anthropic_api_key
        return bool(key)


settings = Settings()
