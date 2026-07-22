"""Точка входа Telegram-бота Mental Club (aiogram 3.x).

Локально — polling. На сервере — webhook (USE_WEBHOOK=true): aiohttp-сервер принимает апдейты,
за ним host nginx (https://<домен>/tg/webhook → 127.0.0.1:WEBHOOK_PORT). Планировщик
напоминаний работает в обоих режимах.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import (BOT_TOKEN, USE_WEBHOOK, WEBHOOK_BASE, WEBHOOK_PATH,
                    WEBHOOK_SECRET, WEBHOOK_PORT)
from api import api
from scheduler import start_scheduler
from handlers import start, intake, flow, test, ask, progress, settings


def _build_dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # порядок важен: state-специфичные роутеры (intake/flow) до общего start (в нём fallback)
    dp.include_router(intake.router)
    dp.include_router(flow.router)
    dp.include_router(test.router)
    dp.include_router(ask.router)
    dp.include_router(progress.router)
    dp.include_router(settings.router)
    dp.include_router(start.router)
    return dp


async def _run_polling(bot: Bot, dp: Dispatcher):
    await bot.delete_webhook(drop_pending_updates=False)   # на случай, если был webhook
    sched = start_scheduler(bot)
    try:
        await dp.start_polling(bot)
    finally:
        sched.shutdown(wait=False)
        await api.close()
        await bot.session.close()


def _run_webhook(bot: Bot, dp: Dispatcher):
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    if not WEBHOOK_BASE:
        raise SystemExit("USE_WEBHOOK=true, но WEBHOOK_BASE не задан")

    async def on_startup(app: web.Application):
        await bot.set_webhook(WEBHOOK_BASE.rstrip("/") + WEBHOOK_PATH,
                              secret_token=WEBHOOK_SECRET or None,
                              drop_pending_updates=False)
        app["sched"] = start_scheduler(bot)
        logging.info("Webhook установлен: %s%s", WEBHOOK_BASE, WEBHOOK_PATH)

    async def on_cleanup(app: web.Application):
        sched = app.get("sched")
        if sched:
            sched.shutdown(wait=False)
        await api.close()
        await bot.session.close()

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    SimpleRequestHandler(dispatcher=dp, bot=bot,
                         secret_token=WEBHOOK_SECRET or None).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=WEBHOOK_PORT)


def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан (переменная окружения)")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = _build_dp()
    if USE_WEBHOOK:
        _run_webhook(bot, dp)          # web.run_app сам управляет циклом
    else:
        asyncio.run(_run_polling(bot, dp))


if __name__ == "__main__":
    main()
