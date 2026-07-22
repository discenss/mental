"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class IntakeStates(StatesGroup):
    answering = State()          # проходит 30 вопросов входной самооценки


class DayStates(StatesGroup):
    running = State()            # проходит шаги дня (маркеры → фокус → задание → квиз → рефлексия)


class SelfcheckStates(StatesGroup):
    answering = State()          # 10 вопросов недельной самопроверки


class PostmoduleStates(StatesGroup):
    answering = State()          # 21 вопрос постмодульного теста (REAL): смежные темы


class FinalProductStates(StatesGroup):
    filling = State()            # пошаговый сбор финального личного продукта (§14)


class AskStates(StatesGroup):
    waiting = State()            # ждёт вопрос к ИИ (текст или голос)


class NoteStates(StatesGroup):
    waiting = State()            # ждёт текст личной заметки в дневник


class SettingsStates(StatesGroup):
    time = State()               # ждёт время напоминания ЧЧ:ММ
    tz = State()                 # ждёт таймзону (напр. Europe/Riga)
