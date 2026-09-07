"""FastAPI-зависимости авторизации.

Ключевое свойство: **авторизация опциональна на уровне транспорта, но обязательна
для владения ресурсом.** Telegram-бот ходит в API как раньше — телом запроса, без
токена, и продолжает работать. iOS-клиент ходит с `Authorization: Bearer <наш JWT>`,
и тогда:

* личность берётся ИЗ ТОКЕНА, а не из тела (тело больше не может назвать чужой user_id);
* `eid` сверяется с владельцем (403 на чужую программу).

Так публичное приложение не открывает дыр, а бот не требует переделки. Когда бота
решат провести через сервисный токен — достаточно заполнить INTERNAL_API_TOKEN и
поднять `require_auth`; точки проверки уже на местах.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.database import get_db
from app.services import auth as auth_svc


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def current_user_id(authorization: str | None = Header(default=None)) -> int | None:
    """user_id из нашего JWT, либо None если токена нет.

    Истёкший/битый токен — это 401, а НЕ «анонимный запрос»: иначе клиент с просроченной
    сессией молча получал бы чужое или пустое состояние вместо явного разлогина.
    """
    token = _bearer(authorization)
    if token is None:
        return None
    try:
        return auth_svc.decode_token(token)
    except auth_svc.AuthDisabled as e:
        raise HTTPException(503, str(e)) from e
    except auth_svc.AuthError as e:
        raise HTTPException(401, str(e)) from e


def require_user_id(user_id: int | None = Depends(current_user_id)) -> int:
    """Строго авторизованный запрос (эндпоинты только для приложения)."""
    if user_id is None:
        raise HTTPException(401, "нужна авторизация")
    return user_id


def is_internal(authorization: str | None = Header(default=None),
                x_internal_token: str | None = Header(default=None)) -> bool:
    """Запрос от доверенного внутреннего клиента (планировщик).

    Пока INTERNAL_API_TOKEN пуст — считаем внутренним любой запрос (текущее поведение,
    бот не сломан). Как только токен задан — только предъявивший его.
    """
    if not settings.internal_api_token:
        return True
    supplied = x_internal_token or _bearer(authorization)
    return bool(supplied) and supplied == settings.internal_api_token


def resolve_user_id(request: Request, db: Session, payload: dict,
                    token_user_id: int | None) -> int:
    """Единая точка опознания пользователя для body-эндпоинтов.

    Токен, если он есть, ПЕРЕБИВАЕТ тело: приложение не может попросить чужой user_id.
    """
    from app.services import identity
    if token_user_id is not None:
        return token_user_id
    if payload.get("provider") and payload.get("provider_user_id") is not None:
        return identity.resolve_or_create(db, payload["provider"],
                                          payload["provider_user_id"]).id
    if payload.get("user_id") is not None:
        return int(payload["user_id"])
    raise HTTPException(422, "нужен user_id или provider+provider_user_id")


def owned_enrollment(db: Session, eid: int, token_user_id: int | None) -> m.Enrollment:
    """Программа по eid + проверка владельца для авторизованных запросов."""
    e = db.get(m.Enrollment, eid)
    if not e:
        raise HTTPException(404, "enrollment not found")
    if token_user_id is not None and e.user_id != token_user_id:
        raise HTTPException(403, "это не ваша программа")
    return e
