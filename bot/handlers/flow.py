"""Дневной flow: маркеры (перекрываются на месте + сводка иконками) → фокус+задание →
квиз → вечерние маркеры → рефлексии. И недельная самопроверка.

Дневной гейт «1 день/сутки» — здесь (клиент). Бэкенд time-agnostic.
"""
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from config import AUDIO_DIR

import texts
from api import api
from keyboards import (MARKER_ICONS, MENU_TEXTS, marker_kb, next_kb, options_kb,
                       skip_kb, skip_wait_kb, task_status_kb)
from states import DayStates, FinalProductStates, PostmoduleStates, SelfcheckStates
from voice import message_text
from handlers.progress import resolve_eid

router = Router()


# ── построение шагов дня ──────────────────────────────────────────────────────

def _task_text(today: dict) -> str:
    task = today["task"]
    txt = task["text"] + ("".join(f"\n• {s}" for s in task.get("subtasks", []))
                          if task.get("subtasks") else "")
    return txt


def _build_morning_steps(today: dict) -> list[dict]:
    """Утренняя сессия: открыть день — утренние маркеры + фокус + показ задания."""
    steps: list[dict] = []
    for mk in today["morning_markers"]:
        steps.append({"kind": "marker", "phase": "morning", "idx": mk["idx"],
                      "question": mk["question"], "options": mk["options"]})
    for q in today.get("intent_questions") or []:           # W6-спец
        steps.append({"kind": "info", "text": f"🎯 {q}"})
    combined = (f"📌 <b>Фокус дня</b>\n{today['focus']}\n\n📝 <b>Задание дня</b>\n{_task_text(today)}"
                "\n\n<i>Занимайтесь днём, а вечером вернитесь закрыть день.</i>")
    steps.append({"kind": "info", "text": combined})
    # §8.4 — аудио отдельным сообщением: кнопка «Слушать» НЕ убирается при «Далее»
    if today.get("audio"):
        a = today["audio"]
        steps.append({"kind": "audio", "code": a["code"], "title": a.get("title"),
                      "media_filename": a.get("media_filename"), "tg_file_id": a.get("tg_file_id")})
    return steps


def _build_evening_steps(today: dict) -> list[dict]:
    """Вечерняя сессия: закрыть день — статус задания + квиз + вечерние маркеры + рефлексия."""
    steps: list[dict] = []
    steps.append({"kind": "focustask",
                  "text": f"📝 <b>Задание дня</b>\n{_task_text(today)}\n\nКак прошло сегодня?"})
    quiz = today.get("quiz") or {}
    if quiz.get("question"):
        steps.append({"kind": "quiz", "question": quiz["question"], "options": quiz.get("options", [])})
    for mk in today["evening_markers"]:
        steps.append({"kind": "marker", "phase": "evening", "idx": mk["idx"],
                      "question": mk["question"], "options": mk["options"]})
    for q in today.get("reflection", []):
        steps.append({"kind": "free_text", "prompt": q})
    return steps


def _phase_summary(phase: str, answers: dict, opts: dict) -> str:
    head = "☀️ Утро:" if phase == "morning" else "🌙 Вечер:"
    icons = []
    for idx in sorted(opts):
        ci = answers.get(str(idx))
        if ci is None:
            icons.append("·")
            continue
        label = opts[idx][ci] if ci < len(opts[idx]) else ""
        icons.append(MARKER_ICONS.get(label, "·"))
    return f"{head} {' '.join(icons)}"


# ── запуск дня ────────────────────────────────────────────────────────────────

async def show_today(target: Message, state: FSMContext, eid: int, *, force: bool = False):
    data = await state.get_data()
    mode = data.get("mode", "normal")
    today = await api.today(eid)
    st = today["status"]
    if st == "completed":
        await target.answer(
            "🏁 Модуль пройден. Спасибо за эту работу с собой.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📜 Собрать личный продукт", callback_data="finalproduct")],
                [InlineKeyboardButton(text="🧭 Смежные направления", callback_data="postmodule")],
                [InlineKeyboardButton(text="🪞 Итог модуля (ИИ)", callback_data="insight")]]))
        return
    if st == "selfcheck_due":
        await target.answer(
            f"Неделя {today['week']} пройдена. Пора подвести итоги.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🧾 Пройти самопроверку", callback_data="sc_start")]]))
        return
    session = today.get("session", "morning")
    if session == "morning":
        if today.get("done_today") and not force:         # день уже закрывали сегодня
            await target.answer(texts.COME_BACK_TOMORROW,
                                reply_markup=skip_wait_kb())
            return
        # начало недели — показываем клиентский вводный экран недели (один раз, в день 1)
        if today.get("day") == 1 and today.get("week_intro"):
            await target.answer(texts.week_intro(today["week_intro"]))
        steps = _build_morning_steps(today)
        header = f"🌅 Открываем день. Неделя {today['week']}, день {today['day']}: <b>{today['day_title']}</b>"
    else:
        steps = _build_evening_steps(today)
        header = f"🌇 Закрываем день. Неделя {today['week']}, день {today['day']}: <b>{today['day_title']}</b>"
    mopts = {mk["idx"]: mk["options"] for mk in today["morning_markers"]}
    eopts = {mk["idx"]: mk["options"] for mk in today["evening_markers"]}
    await state.update_data(eid=eid, day_session=session, day_steps=steps, day_i=0,
                            day_mopts=mopts, day_eopts=eopts, day_active=True,
                            day_morning={}, day_evening={}, day_task_status=None,
                            day_quiz=None, day_reflection=[])
    await state.set_state(DayStates.running)
    await target.answer(header)
    await _render_new(target, state)


async def resume_if_active(target: Message, state: FSMContext) -> bool:
    """Если день начат, но прерван (ушли в меню/ИИ) — вернуть на текущий шаг."""
    data = await state.get_data()
    if data.get("day_active") and data.get("day_steps"):
        await state.set_state(DayStates.running)
        await target.answer("↩️ Продолжаем день — вот текущий шаг:")
        await _render_new(target, state)
        return True
    return False


@router.callback_query(F.data == "resume_day")
async def cb_resume_day(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await resume_if_active(cb.message, state):
        await cb.message.answer("Активного дня нет. Откройте «📅 Сегодня».")


@router.callback_query(F.data == "dwait_skip")
async def cb_skip_wait(cb: CallbackQuery, state: FSMContext):
    """Пропустить ожидание: сразу открыть вечернюю часть или следующий день (без гейта)."""
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    eid = await resolve_eid(cb.from_user.id, state)
    if not eid:
        await cb.message.answer("Активной программы нет. Откройте «📅 Сегодня».")
        return
    await show_today(cb.message, state, eid, force=True)


async def _render_new(target: Message, state: FSMContext):
    """Отрисовать текущий шаг НОВЫМ сообщением (начало блока / некарточный шаг)."""
    data = await state.get_data()
    step = data["day_steps"][data["day_i"]]
    k = step["kind"]
    if k == "marker":
        emoji = "☀️" if step["phase"] == "morning" else "🌙"
        await target.answer(f"{emoji} {step['question']}", reply_markup=marker_kb(step["options"], "mk"))
    elif k == "quiz":
        await target.answer(f"❓ {step['question']}", reply_markup=options_kb(step["options"], "qz"))
    elif k == "focustask":
        await target.answer(step["text"], reply_markup=task_status_kb())
    elif k == "info":
        await target.answer(step["text"], reply_markup=next_kb())
    elif k == "audio":
        # аудио-шаг: кнопка «Слушать» + «Далее»; при «Далее» разметку НЕ убираем,
        # чтобы кнопка «Слушать» осталась в чате и запись не «пропадала»
        title = step.get("title") or "Аудио-практика"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Слушать аудио дня", callback_data="daudio")],
            [InlineKeyboardButton(text="Далее ▶️", callback_data="daudio_next")]])
        await target.answer(f"🎧 <b>{title}</b>\nАудио-практика дня — можно слушать в любой момент.",
                            reply_markup=kb)
    elif k == "free_text":
        await target.answer(f"✍️ {step['prompt']}\n\n<i>Ответьте текстом или надиктуйте голосовым 🎤</i>",
                            reply_markup=skip_kb())


async def _next_new(target: Message, state: FSMContext):
    """Перейти к следующему шагу новым сообщением (или завершить день)."""
    data = await state.get_data()
    i = data["day_i"] + 1
    if i >= len(data["day_steps"]):
        await _finish_day(target, state)
        return
    await state.update_data(day_i=i)
    await _render_new(target, state)


async def _finish_day(target: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "normal")
    eid = data["eid"]
    await state.update_data(day_active=False)            # день больше не в процессе
    if data.get("day_session") == "morning":
        await api.open_day(eid, morning=data["day_morning"])
        await state.set_state(None)
        # утро закрыто — предлагаем подождать вечера ИЛИ пропустить ожидание (всем)
        await target.answer(texts.DAY_OPENED, reply_markup=skip_wait_kb())
        return
    # вечер — закрываем день
    res = await api.close_day(
        eid, evening=data["day_evening"], task_status=data["day_task_status"],
        quiz_answer=data["day_quiz"], reflection=data["day_reflection"],
    )
    await state.set_state(None)
    status = res.get("status")
    if status == "selfcheck_due":
        await show_today(target, state, eid)
    else:
        # день закрыт — подождать завтра ИЛИ пропустить ожидание к следующему дню (всем)
        await target.answer(texts.DAY_DONE, reply_markup=skip_wait_kb())


# ── маркеры (перекрываются на месте, в конце блока — сводка) ───────────────────

@router.callback_query(DayStates.running, F.data.startswith("mk:"))
async def cb_marker(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    i = data["day_i"]
    step = data["day_steps"][i]
    phase = step["phase"]
    key = "day_" + phase
    answers = data[key]
    answers[str(step["idx"])] = idx
    await state.update_data(**{key: answers})
    await cb.answer()

    steps = data["day_steps"]
    nxt = steps[i + 1] if i + 1 < len(steps) else None
    if nxt and nxt["kind"] == "marker" and nxt["phase"] == phase:
        # тот же блок — следующий вопрос перекрывает текущий
        await state.update_data(day_i=i + 1)
        emoji = "☀️" if phase == "morning" else "🌙"
        await cb.message.edit_text(f"{emoji} {nxt['question']}",
                                   reply_markup=marker_kb(nxt["options"], "mk"))
        return
    # конец блока маркеров — замораживаем карточку в сводку иконками
    opts = data["day_mopts"] if phase == "morning" else data["day_eopts"]
    await cb.message.edit_text(_phase_summary(phase, answers, opts))
    await _next_new(cb.message, state)


# ── квиз ──────────────────────────────────────────────────────────────────────

@router.callback_query(DayStates.running, F.data.startswith("qz:"))
async def cb_quiz(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    step = data["day_steps"][data["day_i"]]
    chosen = step["options"][idx] if idx < len(step["options"]) else str(idx)
    await state.update_data(day_quiz=chosen)
    await cb.answer()
    await cb.message.edit_text(f"❓ {step['question']}\n✔️ <i>{chosen}</i>")
    await _next_new(cb.message, state)


# ── фокус+задание (статус) и info ──────────────────────────────────────────────

@router.callback_query(DayStates.running, F.data.startswith("task:"))
async def cb_task(cb: CallbackQuery, state: FSMContext):
    status = cb.data.split(":")[1]
    await state.update_data(day_task_status=status)
    label = {"DONE": "✅ Сделано", "PARTIAL": "◻️ Частично", "NOT_DONE": "✖️ Не сделано"}.get(status, status)
    data = await state.get_data()
    await cb.answer()
    await cb.message.edit_text(data["day_steps"][data["day_i"]]["text"] + f"\n\n<b>{label}</b>")
    await _next_new(cb.message, state)


@router.callback_query(DayStates.running, F.data == "daudio")
async def cb_audio(cb: CallbackQuery, state: FSMContext):
    """Прислать аудио-практику дня. Кнопки на сообщении НЕ трогаем — можно переслушать."""
    data = await state.get_data()
    step = data["day_steps"][data["day_i"]]
    if step.get("kind") != "audio":
        await cb.answer()
        return
    await cb.answer("Отправляю аудио…")
    title = step.get("title") or "Аудио-практика"
    if step.get("tg_file_id"):
        await cb.message.answer_audio(step["tg_file_id"], title=title)
        return
    fname = step.get("media_filename")
    path = (AUDIO_DIR / fname) if fname else None
    if not path or not path.is_file():
        await cb.message.answer("🎧 Аудио пока недоступно для этого дня.")
        return
    sent = await cb.message.answer_audio(FSInputFile(path), title=title)
    # закэшировать file_id, чтобы дальше слать мгновенно (и не гонять файл с диска)
    if sent.audio and sent.audio.file_id:
        try:
            await api.set_audio_file_id(step["code"], sent.audio.file_id)
            step["tg_file_id"] = sent.audio.file_id
            await state.update_data(day_steps=data["day_steps"])
        except Exception:
            pass  # кэш — не критично; при сбое просто отправим файл снова в следующий раз


@router.callback_query(DayStates.running, F.data == "daudio_next")
async def cb_audio_next(cb: CallbackQuery, state: FSMContext):
    """«Далее» с аудио-шага: НЕ убираем кнопки (аудио остаётся доступным), просто дальше."""
    await cb.answer()
    await _next_new(cb.message, state)


@router.callback_query(DayStates.running, F.data == "dnext")
async def cb_next(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _next_new(cb.message, state)


# ── рефлексии (свободный текст / голос) ────────────────────────────────────────

@router.callback_query(DayStates.running, F.data == "dskip")
async def cb_skip(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data["day_steps"][data["day_i"]]["kind"] != "free_text":
        await cb.answer()
        return
    refl = data["day_reflection"]
    refl.append("")
    await state.update_data(day_reflection=refl)
    await cb.answer("Пропущено")
    await cb.message.edit_reply_markup(reply_markup=None)
    await _next_new(cb.message, state)


@router.message(DayStates.running)
async def msg_free_text(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:                            # кнопка меню — выходим из дня, пропускаем дальше
        await state.set_state(None)
        raise SkipHandler()
    data = await state.get_data()
    if data["day_steps"][data["day_i"]]["kind"] != "free_text":
        return
    if msg.text == "/skip":
        text = ""
    else:
        text = await message_text(msg)                   # голос → Whisper, иначе текст
        if text is None:
            return
    refl = data["day_reflection"]
    refl.append(text)
    await state.update_data(day_reflection=refl)
    await _next_new(msg, state)


# ── недельная самопроверка ────────────────────────────────────────────────────

@router.callback_query(F.data == "sc_start")
async def cb_selfcheck_start(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    eid = data.get("eid")
    payload = await api.selfcheck_questions(eid)
    await state.update_data(sc_questions=payload["questions"], sc_idx=0, sc_answers={})
    await state.set_state(SelfcheckStates.answering)
    await cb.answer()
    q = payload["questions"][0]
    sent = await cb.message.answer(f"🧾 Итоги недели — вопрос 1/{len(payload['questions'])}\n\n{q['question']}",
                                   reply_markup=options_kb(q["options"], "sc"))
    await state.update_data(sc_msg_id=sent.message_id)


@router.callback_query(SelfcheckStates.answering, F.data.startswith("sc:"))
async def cb_sc_answer(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    qs, i = data["sc_questions"], data["sc_idx"]
    answers = data["sc_answers"]
    answers[str(qs[i]["q"])] = idx
    await cb.answer()
    if i + 1 < len(qs):
        # следующий вопрос самопроверки перекрывает текущий (как в онбординге)
        await state.update_data(sc_idx=i + 1, sc_answers=answers)
        await cb.message.edit_text(f"🧾 Итоги недели — вопрос {i + 2}/{len(qs)}\n\n{qs[i + 1]['question']}",
                                   reply_markup=options_kb(qs[i + 1]["options"], "sc"))
        return
    await cb.message.edit_text("🧾 Подвожу итоги недели…")
    res = await api.selfcheck(data["eid"], {int(k): v for k, v in answers.items()})
    await state.set_state(None)
    await cb.message.answer(
        texts.selfcheck_result(res),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🪞 Разбор недели (ИИ)", callback_data="week_insight")]]))


@router.callback_query(F.data == "week_insight")
async def cb_week_insight(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    eid = data.get("eid")
    if not eid:
        await cb.answer("Нет активной программы", show_alert=True)
        return
    await cb.answer("Собираю разбор…")
    r = await api.week_insight(eid)
    await cb.message.answer(r["text"])


# ── постмодуль: смежные направления (§15) ─────────────────────────────────────

@router.callback_query(F.data == "postmodule")
async def cb_postmodule_start(cb: CallbackQuery, state: FSMContext):
    """После завершения модуля: REAL — тест 21 вопрос; BOUND — сразу маршрут по флагам."""
    data = await state.get_data()
    eid = data.get("eid")
    if not eid:
        await cb.answer("Нет активной программы", show_alert=True)
        return
    await cb.answer()
    payload = await api.postmodule_questions(eid)
    kind = payload.get("kind")

    if kind == "flags":                                   # BOUND — вопросов нет
        res = await api.postmodule(eid)
        await cb.message.answer(texts.postmodule_result(res))
        return
    if kind != "test":                                    # none — у модуля нет постмодуля
        await cb.message.answer("Для этой программы смежные направления не предусмотрены.")
        return

    # REAL — разворачиваем 7 тем × 3 вопроса в линейный список, помним тег каждого
    flat = []
    for t in payload["topics"]:
        for q in t["questions"]:
            flat.append({"tag": t["tag"], "question": q["question"], "options": q["options"]})
    await state.update_data(pm_flat=flat, pm_idx=0, pm_answers={})
    await state.set_state(PostmoduleStates.answering)
    q0 = flat[0]
    await cb.message.answer(
        "🧭 <b>Смежные направления</b>\nНесколько вопросов, чтобы подсказать, какая тема "
        "может быть близка следующей. Это не отменяет пройденное — только ориентир.\n\n"
        f"Вопрос 1/{len(flat)}\n\n{q0['question']}",
        reply_markup=options_kb(q0["options"], "pm"))


@router.callback_query(PostmoduleStates.answering, F.data.startswith("pm:"))
async def cb_pm_answer(cb: CallbackQuery, state: FSMContext):
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    flat, i = data["pm_flat"], data["pm_idx"]
    answers = data["pm_answers"]                            # {tag: [i,i,i]}
    tag = flat[i]["tag"]
    answers.setdefault(tag, []).append(idx)
    await cb.answer()
    if i + 1 < len(flat):
        await state.update_data(pm_idx=i + 1, pm_answers=answers)
        nq = flat[i + 1]
        await cb.message.edit_text(f"🧭 Смежные направления — вопрос {i + 2}/{len(flat)}\n\n{nq['question']}",
                                   reply_markup=options_kb(nq["options"], "pm"))
        return
    await cb.message.edit_text("🧭 Собираю ориентир…")
    res = await api.postmodule(data["eid"], answers)
    await state.set_state(None)
    await cb.message.answer(texts.postmodule_result(res))


# ── финальный личный продукт (§14) ────────────────────────────────────────────

async def _fp_show_section(target: Message, state: FSMContext):
    """Показать текущую секцию продукта (заголовок + подсказка) и ждать ответ/пропуск."""
    data = await state.get_data()
    secs, i = data["fp_sections"], data["fp_idx"]
    sec = secs[i].strip()
    await target.answer(
        f"📜 <b>{data['fp_title']}</b>  ({i + 1}/{len(secs)})\n\n{sec}\n\n"
        "<i>Ответьте текстом, надиктуйте голосом 🎤 или пропустите.</i>",
        reply_markup=skip_kb())


@router.callback_query(F.data == "finalproduct")
async def cb_finalproduct_start(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    eid = data.get("eid")
    if not eid:
        await cb.answer("Нет активной программы", show_alert=True)
        return
    await cb.answer()
    tpl = await api.final_product_template(eid)
    if not tpl.get("exists") or not tpl.get("sections"):
        await cb.message.answer("Для этой программы личный продукт не предусмотрен.")
        return
    await state.update_data(fp_title=tpl["title"], fp_sections=tpl["sections"],
                            fp_idx=0, fp_answers=[])
    await state.set_state(FinalProductStates.filling)
    await cb.message.answer(
        f"📜 <b>{tpl['title']}</b>\nСоберём ваш личный итог модуля — по одному пункту. "
        "Это ваши слова, а не теория; любой пункт можно пропустить и вернуться позже.")
    await _fp_show_section(cb.message, state)


@router.callback_query(FinalProductStates.filling, F.data == "dskip")
async def cb_fp_skip(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Пропущено")
    await cb.message.edit_reply_markup(reply_markup=None)
    await _fp_advance(cb.message, state, "")


@router.message(FinalProductStates.filling)
async def msg_fp_fill(msg: Message, state: FSMContext):
    if msg.text in MENU_TEXTS:                            # кнопка меню — выходим из сбора
        await state.set_state(None)
        raise SkipHandler()
    if msg.text == "/skip":
        text = ""
    else:
        text = await message_text(msg)                   # голос → Whisper, иначе текст
        if text is None:
            return
    await _fp_advance(msg, state, text)


async def _fp_advance(target: Message, state: FSMContext, answer: str):
    data = await state.get_data()
    answers = data["fp_answers"]
    answers.append(answer)
    i = data["fp_idx"] + 1
    if i < len(data["fp_sections"]):
        await state.update_data(fp_idx=i, fp_answers=answers)
        await _fp_show_section(target, state)
        return
    # все секции пройдены — сохранить (instance + дневник) и показать собранное
    await state.update_data(fp_answers=answers)
    res = await api.final_product_save(data["eid"], answers)
    await state.set_state(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📎 Скачать как файл (.md)", callback_data=f"achfile:{data['eid']}")]])
    await target.answer(
        "✅ Готово! Ваш личный итог сохранён в «🏆 Личные достижения» "
        "(раздел «🧭 Мой путь»).\n\n" + res["text"], reply_markup=kb)
