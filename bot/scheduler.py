"""Лёгкий планировщик напоминаний Mental Club.

Раз в минуту спрашивает у бэкенда, кому пора напомнить (тот считает по таймзоне
пользователя, активной записи и «не пройден сегодня», и сам дедупит раз в день),
и шлёт короткий пинг в Telegram. Вся логика — на бэкенде; здесь только отправка.
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api import api
import texts

logger = logging.getLogger(__name__)


async def _tick(bot: Bot) -> None:
    try:
        due = await api.reminders_due()
    except Exception as e:                              # noqa: BLE001
        logger.warning("reminders_due недоступен: %s", e)
        return
    for item in due:
        chat_id = str(item["provider_user_id"])
        slot = item.get("slot")
        if not chat_id.lstrip("-").isdigit():           # тестовые/нетелеграмные id — пропускаем
            continue
        try:
            await bot.send_message(int(chat_id), texts.reminder_nudge(item))
            await api.mark_reminded(chat_id, slot)       # стемп ТОЛЬКО после доставки
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # чат недоступен (заблокировал/не найден) — помечаем, чтобы не долбить весь день
            logger.info("Напоминание не доставлено %s: %s", chat_id, type(e).__name__)
            try:
                await api.mark_reminded(chat_id, slot)
            except Exception:
                pass
        except Exception as e:                          # noqa: BLE001 — сеть/бот: НЕ стемпим, повторим
            logger.warning("Ошибка отправки напоминания %s: %s (повторю в след. тик)", chat_id, e)


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(_tick, "interval", minutes=1, args=[bot], id="reminders",
                  max_instances=1, coalesce=True)
    sched.start()
    logger.info("Планировщик напоминаний запущен (интервал 1 мин)")
    return sched
