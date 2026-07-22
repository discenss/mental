"""ИИ: свободный вопрос (будни, простая модель) + итог модуля (аналитика)."""
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from api import api
from keyboards import MENU_TEXTS, resume_day_kb
from states import AskStates
from voice import message_text

router = Router()


@router.message(F.text == "🤖 Спросить ИИ")
async def ask_start(msg: Message, state: FSMContext):
    await state.set_state(AskStates.waiting)
    await msg.answer("Напишите или наговорите вопрос — отвечу спокойно и по делу. "
                     "Это не терапия и не диагноз.")


@router.message(AskStates.waiting)
async def ask_answer(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:                            # кнопка меню — выходим, пропускаем дальше
        await state.set_state(None)
        raise SkipHandler()
    q = await message_text(msg)                          # голос → Whisper
    if not q:
        return
    await msg.answer("Думаю…")
    r = await api.ask(msg.from_user.id, q)
    await state.set_state(None)
    data = await state.get_data()
    kb = resume_day_kb() if data.get("day_active") else None   # был прерван день — вернём
    await msg.answer(r["text"], reply_markup=kb)


@router.callback_query(F.data == "insight")
async def cb_insight(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    eid = data.get("eid")
    if not eid:
        await cb.answer("Нет активного модуля", show_alert=True)
        return
    await cb.answer("Собираю итог…")
    r = await api.insight(eid)
    await cb.message.answer(r["text"])
