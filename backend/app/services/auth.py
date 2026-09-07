"""Авторизация мобильного клиента: Apple/Google Sign-In → свой JWT.

Область действия — ТОЛЬКО iOS-клиент. Telegram-бот не затронут: он продолжает
обращаться к API телом запроса (`provider`+`provider_user_id` / `user_id`) без токена.
Поэтому проверки здесь «мягкие по умолчанию»: если запрос пришёл с токеном, личность
берётся из токена и владение ресурсом проверяется; если токена нет — старое поведение.

Схема: клиент получает identity token у Apple/Google → мы верифицируем его подпись по
JWKS провайдера (issuer/audience/срок) → резолвим единого User через identity-слой →
выдаём собственный JWT (HS256), который iOS хранит в Keychain.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.services import identity

# Провайдер-значения в user_identities. "ios" уже был в identity.PROVIDERS (Apple),
# "google" добавлен туда же — см. identity.PROVIDERS.
APPLE_PROVIDER = "ios"
GOOGLE_PROVIDER = "google"

# JWKS-клиенты кэшируют ключи сами; держим по одному на провайдера.
_jwk_clients: dict[str, PyJWKClient] = {}


class AuthError(Exception):
    """Токен провайдера не прошёл проверку (→ 401 на уровне API)."""


class AuthDisabled(Exception):
    """Авторизация не настроена (нет JWT_SECRET / audience) (→ 503)."""


def _jwk_client(url: str) -> PyJWKClient:
    client = _jwk_clients.get(url)
    if client is None:
        # lifespan подобран так, чтобы ротация ключей провайдера подхватывалась сама
        client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwk_clients[url] = client
    return client


def _verify_provider_token(token: str, *, jwks_url: str, audiences: list[str],
                           issuers: list[str]) -> dict:
    """Проверить подпись identity token провайдера и вернуть его payload."""
    if not audiences:
        raise AuthDisabled("не заданы допустимые audience для этого провайдера")
    try:
        key = _jwk_client(jwks_url).get_signing_key_from_jwt(token).key
    except Exception as e:                                          # noqa: BLE001
        raise AuthError(f"не удалось получить ключ подписи: {e}") from e
    last: Exception | None = None
    # audience проверяем перебором: у dev/beta/release разные bundle id
    for aud in audiences:
        try:
            return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=aud,
                              options={"require": ["exp", "iat", "sub"]})
        except jwt.InvalidAudienceError as e:
            last = e
            continue
        except jwt.PyJWTError as e:
            raise AuthError(f"токен провайдера отклонён: {e}") from e
    raise AuthError(f"audience токена не входит в список разрешённых: {last}")


def verify_apple(token: str) -> dict:
    """Apple identity token → {provider_user_id, email?}."""
    payload = _verify_provider_token(
        token, jwks_url=settings.apple_jwks_url,
        audiences=settings.apple_audiences, issuers=[settings.apple_issuer])
    if payload.get("iss") != settings.apple_issuer:
        raise AuthError("неверный issuer Apple-токена")
    return {"provider": APPLE_PROVIDER, "provider_user_id": payload["sub"],
            "email": payload.get("email")}


def verify_google(token: str) -> dict:
    """Google id_token → {provider_user_id, email?}."""
    payload = _verify_provider_token(
        token, jwks_url=settings.google_jwks_url,
        audiences=settings.google_audiences, issuers=settings.google_allowed_issuers)
    if payload.get("iss") not in settings.google_allowed_issuers:
        raise AuthError("неверный issuer Google-токена")
    return {"provider": GOOGLE_PROVIDER, "provider_user_id": payload["sub"],
            "email": payload.get("email")}


# ── свой токен сессии ────────────────────────────────────────────────────────

def issue_token(user_id: int) -> dict:
    """Выдать наш JWT (его iOS кладёт в Keychain)."""
    if not settings.auth_enabled:
        raise AuthDisabled("JWT_SECRET не задан — авторизация не настроена")
    now = datetime.now(UTC)
    exp = now + timedelta(days=settings.jwt_ttl_days)
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {"access_token": token, "token_type": "bearer",
            "expires_at": exp.isoformat(), "user_id": user_id}


def decode_token(token: str) -> int:
    """Наш JWT → user_id. Бросает AuthError на истёкшем/битом токене (→ 401)."""
    if not settings.auth_enabled:
        raise AuthDisabled("JWT_SECRET не задан — авторизация не настроена")
    try:
        payload = jwt.decode(token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm],
                             options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as e:
        raise AuthError("срок действия сессии истёк") from e
    except jwt.PyJWTError as e:
        raise AuthError(f"недействительный токен: {e}") from e
    return int(payload["sub"])


def sign_in(db: Session, provider_result: dict, *, language: str = "ru",
            timezone: str | None = None) -> dict:
    """Верифицированный результат провайдера → единый User + наш JWT."""
    user = identity.resolve_or_create(
        db, provider_result["provider"], provider_result["provider_user_id"],
        language=language, timezone=timezone)
    out = issue_token(user.id)
    out["language"] = user.preferred_language
    return out
