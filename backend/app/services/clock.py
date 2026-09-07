"""Локальная дата пользователя.

Дневной гейт («один день в сутки») раньше считался по `date.today()` серверного
процесса: для пользователя в другой таймзоне «новый день» наступал не в его полночь,
а в серверную. Движок напоминаний при этом уже уважал `User.timezone` — то есть
напоминание и гейт жили по разным часам. Здесь единый источник локальной даты,
одинаковый для обоих.
"""
from __future__ import annotations

from datetime import date as _date, datetime

import pytz

DEFAULT_TZ = "Europe/Riga"


def tz(name: str | None) -> pytz.BaseTzInfo:
    try:
        return pytz.timezone(name or DEFAULT_TZ)
    except Exception:                                       # noqa: BLE001
        return pytz.timezone(DEFAULT_TZ)


def today_for(user) -> _date:
    """Календарная дата «сейчас» в таймзоне пользователя."""
    tzinfo = tz(getattr(user, "timezone", None) if user is not None else None)
    return datetime.now(pytz.utc).astimezone(tzinfo).date()
