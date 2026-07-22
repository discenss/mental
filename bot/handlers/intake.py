"""Входная самооценка — 30 вопросов, шкала 0–4 (§12)."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts
from api import api
from keyboards import intake_result_kb, scale_kb
from states import IntakeStates

router = Router()


def _q_text(i: int, total: int, q: dict) -> str:
    return f"Вопрос {i + 1}/{total}\n\n{q['text']}"


async def begin_intake(msg: Message, state: FSMContext):
    data = await api.intake_questions()
    await state.update_data(iq_questions=data["questions"], iq_scale=data["answer_scale"],
                            iq_idx=0, iq_answers={})
    await state.set_state(IntakeStates.answering)
    await msg.answer("🧭 " + data.get("client_intro", ""))
    # первый вопрос — отдельным сообщением; дальше оно редактируется на месте
    q0 = data["questions"][0]
    sent = await msg.answer(_q_text(0, len(data["questions"]), q0),
                            reply_markup=scale_kb(data["answer_scale"], "iq"))
    await state.update_data(iq_msg_id=sent.message_id)


@router.callback_query(IntakeStates.answering, F.data.startswith("iq:"))
async def cb_answer(cb: CallbackQuery, state: FSMContext):
    val = int(cb.data.split(":")[1])
    data = await state.get_data()
    qs, i = data["iq_questions"], data["iq_idx"]
    answers = data["iq_answers"]
    answers[str(qs[i]["n"])] = val
    await cb.answer()
    if i + 1 < len(qs):
        # следующий вопрос перекрывает текущий (редактируем то же сообщение)
        await state.update_data(iq_idx=i + 1, iq_answers=answers)
        await cb.message.edit_text(_q_text(i + 1, len(qs), qs[i + 1]),
                                   reply_markup=scale_kb(data["iq_scale"], "iq"))
        return
    # все ответы собраны → результат
    await cb.message.edit_text("🧭 Собираю ваш результат…")
    ans = {int(k): v for k, v in answers.items()}
    r = await api.submit_intake(cb.from_user.id, ans)
    await state.set_state(None)
    await cb.message.answer(texts.intake_result(r), reply_markup=intake_result_kb(r))
