"""⚙️ Настройки: напоминания (вкл/выкл, время, часовой пояс)."""
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from api import api
from keyboards import MENU_TEXTS, settings_kb, language_kb, LANGUAGE_LABELS
from states import SettingsStates

router = Router()


async def _show(target: Message, tg_id: int):
    s = await api.get_settings(tg_id)
    await target.answer(texts.settings_view(s), reply_markup=settings_kb(s))


@router.message(F.text == "⚙️ Настройки")
async def menu_settings(msg: Message, state: FSMContext):
    await state.set_state(None)
    await _show(msg, msg.from_user.id)


_SLOT_LABEL = {"morning": "утреннего опроса", "afternoon": "напоминания о задании",
               "evening": "вечернего опроса"}


@router.callback_query(F.data.startswith("set_time:"))
async def cb_set_time(cb: CallbackQuery, state: FSMContext):
    slot = cb.data.split(":")[1]
    await state.set_state(SettingsStates.time)
    await state.update_data(set_slot=slot)
    await cb.answer()
    await cb.message.answer(f"Во сколько присылать напоминание для «{_SLOT_LABEL.get(slot, slot)}»? "
                            "Пришлите время в формате <b>ЧЧ:ММ</b> (например, 10:00). /cancel — отмена.")


@router.message(SettingsStates.time)
async def set_time(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:
        await state.set_state(None)
        raise SkipHandler()
    if msg.text == "/cancel":
        await state.set_state(None)
        await _show(msg, msg.from_user.id)
        return
    raw = (msg.text or "").strip().replace(".", ":").replace(" ", "")
    try:
        hh, mm = raw.split(":")
        hh, mm = int(hh), int(mm)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
    except Exception:
        await msg.answer("Не понял время. Формат <b>ЧЧ:ММ</b>, например 09:00. Ещё раз или /cancel.")
        return
    data = await state.get_data()
    slot = data.get("set_slot", "evening")
    await api.update_settings(msg.from_user.id, slot=slot, hour=hh, minute=mm)
    await state.set_state(None)
    await msg.answer(f"Готово: {_SLOT_LABEL.get(slot, slot)} в {hh:02d}:{mm:02d}.")
    await _show(msg, msg.from_user.id)


@router.callback_query(F.data == "set_tz")
async def cb_set_tz(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.tz)
    await cb.answer()
    await cb.message.answer("Пришлите часовой пояс в формате IANA, например: "
                            "<code>Europe/Riga</code>, <code>Europe/Moscow</code>, "
                            "<code>Asia/Almaty</code>. /cancel — отмена.")


@router.message(SettingsStates.tz)
async def set_tz(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:
        await state.set_state(None)
        raise SkipHandler()
    if msg.text == "/cancel":
        await state.set_state(None)
        await _show(msg, msg.from_user.id)
        return
    tz = (msg.text or "").strip()
    try:
        await api.update_settings(msg.from_user.id, timezone=tz)
    except Exception:                                    # noqa: BLE001 — бэкенд отверг таймзону
        await msg.answer("Не распознал часовой пояс. Пример: <code>Europe/Riga</code>. "
                         "Ещё раз или /cancel.")
        return
    await state.set_state(None)
    await msg.answer(f"Часовой пояс: {tz}.")
    await _show(msg, msg.from_user.id)


@router.callback_query(F.data == "set_lang_menu")
async def cb_set_lang_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer("На каком языке показывать программу?", reply_markup=language_kb())


@router.callback_query(F.data.startswith("set_lang:"))
async def cb_set_lang(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":", 1)[1]
    await api.update_settings(cb.from_user.id, language=code)
    await cb.answer(f"Готово: {LANGUAGE_LABELS.get(code, code)}")
    await _show(cb.message, cb.from_user.id)
