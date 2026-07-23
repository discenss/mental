"""Inline-клавиатуры бота."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# Тексты кнопок главного меню — чтобы «escape» из любого состояния (см. flow/ask/…)
MENU_TEXTS = {
    "📅 Сегодня", "🧭 Мой путь", "📔 Дневник", "🤖 Спросить ИИ", "⚙️ Настройки",
    "📚 Модули", "🔄 Начать заново",
}

# Иконки-градация для маркеров дня (шкала согласия Да…Нет), нейтральные (не «хорошо/плохо»)
MARKER_ICONS = {"Да": "●", "Скорее да": "◕", "Скорее нет": "◔", "Нет": "○"}

# Языки контента (§ многоязычность) — коды должны совпадать с i18n.SUPPORTED_LANGUAGES на бэкенде
LANGUAGE_LABELS = {
    "ru": "🇷🇺 Русский", "en": "🇬🇧 English", "uk": "🇺🇦 Українська",
    "es": "🇪🇸 Español", "de": "🇩🇪 Deutsch",
}


def language_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, label in LANGUAGE_LABELS.items():
        b.button(text=label, callback_data=f"set_lang:{code}")
    b.adjust(1)
    return b.as_markup()


def options_kb(options: list[str], prefix: str) -> InlineKeyboardMarkup:
    """Кнопки-варианты, callback = f'{prefix}:{index}'."""
    b = InlineKeyboardBuilder()
    for i, text in enumerate(options):
        b.button(text=text[:64], callback_data=f"{prefix}:{i}")
    b.adjust(1)
    return b.as_markup()


def marker_kb(options: list[str], prefix: str) -> InlineKeyboardMarkup:
    """Маркеры дня: иконка-градация + подпись, компактно (по 2 в ряд)."""
    b = InlineKeyboardBuilder()
    for i, text in enumerate(options):
        icon = MARKER_ICONS.get(text, "·")
        b.button(text=f"{icon} {text}", callback_data=f"{prefix}:{i}")
    b.adjust(2)
    return b.as_markup()


# Иконки шкалы 0–4: заполнение круга = «насколько это про меня» (без цифр в кнопке)
SCALE_ICONS = {0: "○", 1: "◔", 2: "◑", 3: "◕", 4: "●"}


def scale_kb(scale: list[dict], prefix: str) -> InlineKeyboardMarkup:
    """Шкала интейка 0–4: иконка-градация + подпись, без ведущей цифры."""
    b = InlineKeyboardBuilder()
    for item in scale:
        icon = SCALE_ICONS.get(int(item["value"]), "•")
        b.button(text=f"{icon} {item['label']}", callback_data=f"{prefix}:{item['value']}")
    b.adjust(1)
    return b.as_markup()


def next_kb(cb: str = "dnext", text: str = "Далее ▶️") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=cb)]])


def skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="dskip")]])


def resume_day_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Продолжить день", callback_data="resume_day")]])


def task_status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Сделано", callback_data="task:DONE"),
        InlineKeyboardButton(text="◻️ Частично", callback_data="task:PARTIAL"),
        InlineKeyboardButton(text="✖️ Не сделано", callback_data="task:NOT_DONE"),
    ]])


def intake_result_kb(r: dict) -> InlineKeyboardMarkup:
    """Одна рекомендованная программа + кнопка на остальные маршруты.

    Если модуль по рекомендованному направлению готов → активная «Начать».
    Если ещё не готов → неактивная кнопка «<имя> (скоро)» (тап → тост).
    Всегда есть «🗂 Другие маршруты» — выбор из доступных программ.
    """
    b = InlineKeyboardBuilder()
    lead_code = r.get("leading_module")
    lead_module_name = r.get("leading_module_name")
    lead_dir_name = r.get("leading_name")
    if lead_code and lead_module_name:
        b.button(text=f"▶️ Начать: {lead_module_name}", callback_data=f"enroll:{lead_code}:normal")
    else:
        b.button(text=f"🔒 {lead_dir_name} — скоро", callback_data="route_soon")
    b.button(text="🗂 Другие маршруты", callback_data="show_modules")
    b.adjust(1)
    return b.as_markup()


def modules_kb(modules: list[dict], mode: str = "normal") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for mdl in modules:
        b.button(text=mdl["name"], callback_data=f"enroll:{mdl['code']}:{mode}")
    b.adjust(1)
    return b.as_markup()


def onboard_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Начать", callback_data="onboard_start")]])


def skip_wait_kb() -> InlineKeyboardMarkup:
    """Кнопка пропуска ожидания на экранах «Сегодня» — сразу к следующей сессии/дню.
    Помечена «(тест)»: для отладки/нетерпеливых; доступна всем."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏭ Дальше (тест)", callback_data="dwait_skip")]])


def active_route_kb() -> InlineKeyboardMarkup:
    """Экран при попытке открыть «Модули», когда уже есть активный маршрут."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить программу", callback_data="route_continue")],
        [InlineKeyboardButton(text="🔄 Сменить программу", callback_data="route_switch")],
    ])


def onboard_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧭 Подобрать программу (пройти опрос)", callback_data="go_intake")],
        [InlineKeyboardButton(text="📚 Выбрать программу самому", callback_data="show_modules")],
    ])


def start_day_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="▶️ Открыть первый день", callback_data="start_day")]])


def reset_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, сбросить всё", callback_data="reset_yes"),
        InlineKeyboardButton(text="Отмена", callback_data="reset_no"),
    ]])


def test_menu_kb(eid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏭ Следующий день", callback_data=f"test:day:best")
    b.button(text="⏩ Неделя (лучшие)", callback_data=f"test:week:best")
    b.button(text="⏩ Неделя (худшие)", callback_data=f"test:week:worst")
    b.button(text="⏩⏩ Вся программа (лучшие)", callback_data=f"test:program:best")
    b.button(text="⏩⏩ Вся программа (худшие)", callback_data=f"test:program:worst")
    b.button(text="🎲 Вся программа (случайно)", callback_data=f"test:program:random")
    b.adjust(1)
    return b.as_markup()


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="🧭 Мой путь")],
        [KeyboardButton(text="📔 Дневник"), KeyboardButton(text="🤖 Спросить ИИ")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📚 Модули")],
        [KeyboardButton(text="🔄 Начать заново")],
    ])


def _hhmm(slot: dict) -> str:
    return f"{slot['hour']:02d}:{slot['minute']:02d}"


def settings_kb(s: dict) -> InlineKeyboardMarkup:
    # напоминания всегда включены — переключателя нет, меняется только время/пояс
    b = InlineKeyboardBuilder()
    b.button(text=f"☀️ Утро: {_hhmm(s['morning'])}", callback_data="set_time:morning")
    b.button(text=f"🌤 День: {_hhmm(s['afternoon'])}", callback_data="set_time:afternoon")
    b.button(text=f"🌙 Вечер: {_hhmm(s['evening'])}", callback_data="set_time:evening")
    b.button(text=f"🌍 Часовой пояс: {s['timezone']}", callback_data="set_tz")
    b.button(text=f"{LANGUAGE_LABELS.get(s.get('language', 'ru'), '🌐 Язык')}", callback_data="set_lang_menu")
    b.adjust(1)
    return b.as_markup()


def note_add_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Добавить заметку", callback_data="note_add")]])


def journal_index_kb(days: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """days: [(key 'YYYY-MM-DD', отображение 'DD.MM.YYYY', число записей)], свежие сверху."""
    b = InlineKeyboardBuilder()
    b.button(text="📝 Добавить заметку", callback_data="note_add")
    for key, disp, cnt in days:
        b.button(text=f"📅 {disp} · {cnt}", callback_data=f"jday:{key}")
    b.adjust(1)
    return b.as_markup()


def journal_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ К дневнику", callback_data="jindex")]])
