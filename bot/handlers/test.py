"""Авто-прогон (только тестировщики): перемотка день/неделя/программа пресетами
best/worst/random с дампом выдачи движка. Отдельный инструмент отладки — работает
над ТЕКУЩИМ активным маршрутом пользователя (отдельного тест-enrollment больше нет).

Вызов: команда /test. Обычные пользователи промотку не видят; ожидание между
сессиями снимается кнопкой «⏭ Пропустить ожидание» (доступна всем, см. flow.py).
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from api import api
from config import is_tester
from keyboards import test_menu_kb
from handlers.progress import resolve_eid

router = Router()


@router.message(Command("test"))
async def cmd_test(msg: Message, state: FSMContext):
    """Меню авто-прогона над текущим активным маршрутом (для тестировщиков)."""
    if not is_tester(msg.from_user.id):
        await msg.answer("Команда доступна только тестировщикам.")
        return
    eid = await resolve_eid(msg.from_user.id, state)
    if not eid:
        await msg.answer("Сначала выберите программу в «📚 Модули».")
        return
    await msg.answer("🧪 Авто-прогон текущего маршрута — выберите объём:",
                     reply_markup=test_menu_kb(eid))


@router.callback_query(F.data.startswith("test:"))
async def cb_test_advance(cb: CallbackQuery, state: FSMContext):
    if not is_tester(cb.from_user.id):
        await cb.answer("Только для тестировщиков", show_alert=True)
        return
    _, scope, preset = cb.data.split(":")
    eid = await resolve_eid(cb.from_user.id, state)
    if not eid:
        await cb.answer("Нет активного маршрута", show_alert=True)
        return
    await cb.answer("Прогоняю…")
    r = await api.test_advance(eid, scope, preset)
    for chunk in texts.test_transcript(r):
        await cb.message.answer(chunk)
    if r["status"] == "completed":
        await cb.message.answer("🏁 Программа пройдена (авто-прогон).")
    else:
        await cb.message.answer(f"Позиция: неделя {r['week']}, день {r['day']}.",
                                reply_markup=test_menu_kb(eid))
