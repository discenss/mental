"""Старт, главное меню, каталог модулей, общий enroll-обработчик."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message, ReplyKeyboardRemove)

import texts
from api import api
from keyboards import (active_route_kb, main_menu_kb, modules_kb, onboard_choice_kb,
                       onboard_start_kb, reset_confirm_kb, settings_kb, start_day_kb)
from handlers.intake import begin_intake
from handlers.flow import resume_if_active, show_today
from handlers.progress import resolve_eid

router = Router()


async def _start_screen(msg: Message):
    """Новый/сброшенный пользователь: только кнопка «Начать», без полного меню."""
    await msg.answer(texts.WELCOME_NEW, reply_markup=onboard_start_kb())


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await api.resolve_user(msg.from_user.id)          # создаём/находим пользователя
    await state.set_state(None)
    enrollments = await api.user_enrollments(msg.from_user.id)
    if enrollments:                                    # вернувшийся — сразу меню
        await msg.answer(texts.WELCOME, reply_markup=main_menu_kb())
    else:                                              # новый — мягкий вход
        await _start_screen(msg)


@router.callback_query(F.data == "onboard_start")
async def cb_onboard_start(cb: CallbackQuery):
    await cb.answer()
    # на этом этапе полное меню НЕ показываем — только объяснение сервиса и два пути выбора
    # программы (Сегодня/Спросить ИИ/Модули тут пусты или дублируют выбор). Меню — после записи.
    await cb.message.answer(texts.ONBOARD_INTRO, reply_markup=ReplyKeyboardRemove())
    await cb.message.answer("С чего начнём?", reply_markup=onboard_choice_kb())


@router.callback_query(F.data == "go_intake")
async def cb_go_intake(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await begin_intake(cb.message, state)


@router.message(Command("reset"))
@router.message(F.text == "🔄 Начать заново")
async def cmd_reset(msg: Message, state: FSMContext):
    await msg.answer(
        "♻️ <b>Сброс прогресса</b>\n\nЭто удалит все ваши программы, ответы, дневник и результаты "
        "самопроверок — и позволит начать заново. Действие необратимо. Продолжить?",
        reply_markup=reset_confirm_kb())


@router.callback_query(F.data == "reset_no")
async def cb_reset_no(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("Отменено. Всё на месте.")


@router.callback_query(F.data == "reset_yes")
async def cb_reset_yes(cb: CallbackQuery, state: FSMContext):
    await api.reset_user(cb.from_user.id)
    await state.clear()
    await cb.answer("Готово")
    # убираем полное меню и возвращаем на мягкий стартовый экран
    await cb.message.answer("🗑 Прогресс сброшен.", reply_markup=ReplyKeyboardRemove())
    await _start_screen(cb.message)


@router.message(F.text == "📅 Сегодня")
async def menu_today(msg: Message, state: FSMContext):
    if await resume_if_active(msg, state):               # прерванный день — вернуть на шаг
        return
    eid = await resolve_eid(msg.from_user.id, state)
    if not eid:
        await msg.answer("Сначала выберите программу в «📚 Модули».")
        return
    await show_today(msg, state, eid)


async def _active_enrollment(tg_id: int) -> dict | None:
    """Незавершённая программа пользователя (active/selfcheck_due), если есть."""
    enrollments = await api.user_enrollments(tg_id)
    live = [e for e in enrollments if e["status"] in ("active", "selfcheck_due")]
    return live[0] if live else None


@router.message(F.text == "📚 Модули")
async def menu_modules(msg: Message):
    active = await _active_enrollment(msg.from_user.id)
    if active:
        await msg.answer(texts.on_active_route(active), reply_markup=active_route_kb())
        return
    mods = await api.modules()
    await msg.answer("Выберите программу:", reply_markup=modules_kb(mods, mode="normal"))


@router.callback_query(F.data == "start_day")
async def cb_start_day(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(None)                          # выходим из настроек, если были там
    eid = await resolve_eid(cb.from_user.id, state)
    if not eid:
        await cb.message.answer("Сначала выберите программу в «📚 Модули».")
        return
    await show_today(cb.message, state, eid)


@router.callback_query(F.data == "show_modules")
async def cb_show_modules(cb: CallbackQuery):
    await cb.answer()
    active = await _active_enrollment(cb.from_user.id)
    if active:
        await cb.message.answer(texts.on_active_route(active), reply_markup=active_route_kb())
        return
    mods = await api.modules()
    await cb.message.answer("🗂 Доступные программы — выберите, с чего начать:",
                            reply_markup=modules_kb(mods, mode="normal"))


@router.callback_query(F.data == "route_soon")
async def cb_route_soon(cb: CallbackQuery):
    await cb.answer("Эта программа ещё готовится — скоро откроем. "
                    "Пока можно выбрать одну из доступных программ.", show_alert=True)


@router.callback_query(F.data == "route_continue")
async def cb_route_continue(cb: CallbackQuery, state: FSMContext):
    """«Продолжить» с экрана активного маршрута — на текущий день."""
    await cb.answer()
    if await resume_if_active(cb.message, state):
        return
    eid = await resolve_eid(cb.from_user.id, state)
    if eid:
        await show_today(cb.message, state, eid)


@router.callback_query(F.data == "route_switch")
async def cb_route_switch(cb: CallbackQuery):
    """«Сменить программу» — предупредить о сбросе ТЕКУЩЕЙ программы и спросить подтверждение."""
    await cb.answer()
    active = await _active_enrollment(cb.from_user.id)
    name = active.get("name") if active else "текущая"
    await cb.message.answer(
        f"Сейчас вы на программе «<b>{name}</b>». Смена программы <b>сбросит прогресс по ней</b> "
        "(дни, самопроверки, её записи в дневнике). Пройденные ранее программы останутся в «🧭 Мой путь».\n\n"
        "Продолжить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, сменить программу", callback_data="route_switch_yes")],
            [InlineKeyboardButton(text="↩️ Остаться на текущей", callback_data="route_continue")]]))


@router.callback_query(F.data == "route_switch_yes")
async def cb_route_switch_yes(cb: CallbackQuery, state: FSMContext):
    """Подтверждён сброс текущей программы → чистим и ведём на выбор новой (опрос / модули)."""
    await cb.answer()
    await api.abandon_active(cb.from_user.id)
    await state.update_data(eid=None, module=None)        # забыть старый маршрут в FSM
    await cb.message.answer("Текущая программа сброшена. Выберите новую 👇",
                            reply_markup=onboard_choice_kb())


@router.callback_query(F.data.startswith("enroll:"))
async def cb_enroll(cb: CallbackQuery, state: FSMContext):
    _, code, mode = cb.data.split(":")
    e = await api.enroll(cb.from_user.id, code, mode)
    name = e.get("name", code)
    await state.update_data(eid=e["enrollment_id"], mode=mode, module=code)
    await cb.answer()
    # запись есть → теперь показываем полное меню (Сегодня/Мой путь/Дневник и т.д.)
    await cb.message.answer(
        f"✅ Вы записаны на программу «<b>{name}</b>».\n\n"
        f"Формат простой: 6 недель, по одному дню за раз. Каждый день в две короткие "
        f"сессии — утром «открыть день» (фокус и задание), вечером «закрыть день» "
        f"(как прошло + рефлексия).", reply_markup=main_menu_kb())
    # первый раз — предлагаем настроить напоминания; день НЕ стартуем сами (иначе конфликт)
    s = await api.get_settings(cb.from_user.id)
    await cb.message.answer(
        "⏰ <b>Напоминания</b> — чтобы бот сам напоминал открыть и закрыть день. Настройте "
        "удобное время (по желанию; изменить можно позже в «⚙️ Настройки»):",
        reply_markup=settings_kb(s))
    await cb.message.answer("Когда будете готовы — откройте первый день 👇",
                            reply_markup=start_day_kb())


# ── подстраховка: сообщение, которое никто не обработал ────────────────────────
# Бот на MemoryStorage: при перезапуске состояние «идёт день» теряется, и пользователь
# «залипает» на шаге (кнопки/ввод не срабатывают). Бэкенд знает сессию дня — восстановим.
@router.message()
async def fallback(msg: Message, state: FSMContext):
    if await state.get_state() is not None:
        # мы в известном потоке (например, интейк по кнопкам) — просто подсказать
        await msg.answer("Пожалуйста, воспользуйтесь кнопками выше 👆")
        return
    eid = await resolve_eid(msg.from_user.id, state)
    if eid:
        await msg.answer("Похоже, ход дня потерялся (бывает после перезапуска). Восстанавливаю 👇")
        await show_today(msg, state, eid)
    else:
        await msg.answer("Не совсем понял. Откройте «📅 Сегодня» внизу или наберите /start.")
