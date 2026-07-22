"""«Мой путь» (статус) и «Мой дневник» (§8): чтение прогресса и записей."""
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

import texts
from api import api
from keyboards import MENU_TEXTS, journal_back_kb, journal_index_kb, note_add_kb
from states import NoteStates
from voice import message_text

router = Router()


def pick_enrollment(enrollments: list[dict]) -> dict | None:
    """Активная запись пользователя: сперва незавершённый normal, затем свежий normal, иначе любой."""
    normal = [e for e in enrollments if e.get("mode") != "test"]
    live = [e for e in normal if e["status"] in ("active", "selfcheck_due")]
    return (live or normal or enrollments or [None])[0]


async def resolve_eid(tg_id: int, state: FSMContext) -> int | None:
    """eid из FSM, иначе — по активной записи пользователя (переживает рестарт бота)."""
    data = await state.get_data()
    eid = data.get("eid")
    if eid:
        return eid
    e = pick_enrollment(await api.user_enrollments(tg_id))
    if e:
        await state.update_data(eid=e["enrollment_id"], module=e["module"], mode=e.get("mode", "normal"))
        return e["enrollment_id"]
    return None


@router.message(F.text == "🧭 Мой путь")
async def menu_path(msg: Message, state: FSMContext):
    enrollments = await api.user_enrollments(msg.from_user.id)
    completed = [e for e in enrollments if e["status"] == "completed"]
    active = pick_enrollment([e for e in enrollments if e["status"] in ("active", "selfcheck_due")])

    if not active and not completed:
        await msg.answer("Пока пусто. Выберите программу в «📚 Модули».")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏆 Личные достижения", callback_data="achievements")]])

    if active:
        text = texts.path_status(await api.status(active["enrollment_id"]))
        if completed:
            text += "\n\n" + texts.path_history(completed)
        await msg.answer(text, reply_markup=kb)
    else:
        # активной нет — только история пройденных
        await msg.answer("🧭 <b>Ваш путь</b>\n\n" + texts.path_history(completed) +
                         "\n\nНовую программу можно выбрать в «📚 Модули».", reply_markup=kb)


# ── Личные достижения (финальные продукты модулей, §14) ───────────────────────

@router.callback_query(F.data == "achievements")
async def cb_achievements(cb: CallbackQuery):
    await cb.answer()
    items = await api.final_products_list(cb.from_user.id)
    if not items:
        await cb.message.answer(
            "🏆 <b>Личные достижения</b>\n\nЗдесь появятся ваши личные итоги модулей — "
            "протокол, ориентир или карта, которые вы собираете в конце программы.")
        return
    rows = [[InlineKeyboardButton(text=f"📜 {it['title'] or it['module_name']}",
                                  callback_data=f"ach:{it['enrollment_id']}")] for it in items]
    await cb.message.answer(
        f"🏆 <b>Личные достижения</b>\n\nСобрано итогов: {len(items)}. Откройте любой:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ach:"))
async def cb_achievement_open(cb: CallbackQuery):
    eid = int(cb.data.split(":")[1])
    await cb.answer()
    items = await api.final_products_list(cb.from_user.id)
    it = next((x for x in items if x["enrollment_id"] == eid), None)
    if not it:
        await cb.message.answer("Этот итог не найден.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📎 Скачать как файл (.md)", callback_data=f"achfile:{eid}")]])
    await cb.message.answer(it["text"], reply_markup=kb)


@router.callback_query(F.data.startswith("achfile:"))
async def cb_achievement_file(cb: CallbackQuery):
    eid = int(cb.data.split(":")[1])
    await cb.answer("Готовлю файл…")
    try:
        data = await api.final_product_file_bytes(eid)
    except Exception:
        await cb.message.answer("Не удалось подготовить файл. Попробуйте позже.")
        return
    await cb.message.answer_document(
        BufferedInputFile(data, filename="личный_итог.md"),
        caption="📎 Ваш личный итог — можно сохранить или переслать.")


def _group_by_day(entries: list[dict]) -> list[tuple[str, str, int]]:
    """[(key 'YYYY-MM-DD', 'DD.MM.YYYY', count)] по дате created_at, свежие сверху."""
    counts: dict[str, int] = {}
    for e in entries:
        key = (e.get("created_at") or "")[:10]
        counts[key] = counts.get(key, 0) + 1
    keys = sorted((k for k in counts if k), reverse=True)[:14]
    return [(k, texts._date_disp(k), counts[k]) for k in keys]


async def _show_journal_index(target: Message, tg_id: int):
    entries = await api.journal_list(tg_id)
    days = _group_by_day(entries)
    await target.answer(texts.journal_index(len(entries)), reply_markup=journal_index_kb(days))


@router.message(F.text == "📔 Дневник")
async def menu_journal(msg: Message, state: FSMContext):
    await _show_journal_index(msg, msg.from_user.id)


@router.callback_query(F.data == "jindex")
async def cb_journal_index(cb: CallbackQuery):
    await cb.answer()
    await _show_journal_index(cb.message, cb.from_user.id)


@router.callback_query(F.data.startswith("jday:"))
async def cb_journal_day(cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    entries = [e for e in await api.journal_list(cb.from_user.id)
               if (e.get("created_at") or "")[:10] == key]
    await cb.answer()
    if not entries:
        await cb.message.answer("За этот день записей нет.", reply_markup=journal_back_kb())
        return
    await cb.message.answer(texts.journal_day(texts._date_disp(key), entries),
                            reply_markup=journal_back_kb())


@router.callback_query(F.data == "note_add")
async def cb_note_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NoteStates.waiting)
    await cb.answer()
    await cb.message.answer("Напишите заметку текстом или надиктуйте голосовым 🎤 — "
                            "сохраню её в дневник. /cancel — отмена.")


@router.message(NoteStates.waiting)
async def note_save(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:                            # кнопка меню — выходим, пропускаем дальше
        await state.set_state(None)
        raise SkipHandler()
    if msg.text == "/cancel":
        await state.set_state(None)
        await msg.answer("Отменено.")
        return
    text = await message_text(msg)                       # голос → Whisper, иначе текст
    if not text or not text.strip():
        await msg.answer("Пустая заметка — пришлите текст или голосовое, либо /cancel.")
        return
    text = text.strip()
    data = await state.get_data()
    await api.journal_add(msg.from_user.id, text, module_code=data.get("module"))
    await state.set_state(None)
    await msg.answer("✅ Записал в дневник.")
    await _show_journal_index(msg, msg.from_user.id)
