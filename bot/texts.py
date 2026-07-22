"""Тексты (ru) и форматтеры. i18n uk/en — на будущее."""

ZONE = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}

WELCOME = (
    "Привет! Это Mental Club — спокойные 6-недельные маршруты работы с собой.\n\n"
    "Начните с «🧭 Подобрать маршрут» — 30 коротких вопросов помогут выбрать, "
    "с чего лучше начать. Или откройте «📚 Модули».\n\n"
    "<i>Начать всё заново можно командой /reset.</i>"
)

WELCOME_NEW = (
    "Привет! Это <b>Mental Club</b> 🌿\n\n"
    "Спокойные 6-недельные маршруты работы с собой — шаг за шагом, в вашем темпе.\n\n"
    "Нажмите «Начать», когда будете готовы."
)

ONBOARD_INTRO = (
    "Это сервис психологической поддержки Mental Club. Мы <b>не ставим диагнозов</b> и не заменяем "
    "работу с психологом — а помогаем мягко и постепенно разобраться с собой.\n\n"
    "Чтобы точнее подобрать, с чего начать, можно пройти короткий онбординг — 30 вопросов определят "
    "вашу ведущую тему.\n\n"
    "Если такой необходимости не чувствуете — проходить не обязательно. Можно сразу выбрать готовую "
    "программу из списка модулей."
)

DAY_OPENED = ("🌅 <b>День открыт.</b>\n\nФокус и задание — выше. Занимайтесь днём в своём темпе.\n\n"
              "Вечером возвращайтесь <b>закрыть день</b> — отметить задание, вечерние вопросы и "
              "рефлексию. Открыть вечернюю часть можно в «📅 Сегодня». 🌇")
DAY_DONE = ("✅ <b>День завершён.</b>\n\nНа сегодня всё — спокойно возвращайтесь завтра, "
            "один день за раз. Завтра откроется следующий день, найти его можно в «📅 Сегодня». 🌙")
DAY_DONE_TEST = "✅ День завершён. Тест-режим — дальше без ожидания. ⏩"
COME_BACK_TOMORROW = "Сегодняшний день уже пройден. Возвращайтесь завтра — маршрут идёт в вашем темпе. 🌙"


def intake_result(r: dict) -> str:
    body = "🧭 <b>Ваш результат</b>\n\n" + r["result_text"] + "\n\n" + r["must_include"]
    if r.get("leading_module") and r.get("leading_module_name"):
        cta = (f"\n\n👉 Рекомендуем начать с программы «<b>{r['leading_module_name']}</b>». "
               f"Нажмите кнопку ниже, чтобы начать. Другие маршруты — рядом.")
    else:
        cta = (f"\n\n👉 По вашим ответам ближе всего маршрут «<b>{r['leading_name']}</b>» — "
               f"эта программа готовится и скоро откроется. "
               f"Пока можно выбрать один из доступных маршрутов кнопкой ниже.")
    return body + cta


SOURCE_LABEL = {"reflection": "✍️ Рефлексия", "task": "📝 Задание",
                "final_product": "🏆 Достижение", "note": "🗒 Заметка"}


def on_active_route(e: dict) -> str:
    """Сообщение при попытке выбрать программу, когда уже идёт активный маршрут."""
    name = e.get("name", e.get("module", ""))
    wk, day = e.get("week"), e.get("day")
    where = f" (неделя {wk}, день {day})" if wk and day else ""
    if e.get("status") == "selfcheck_due":
        where = f" (неделя {wk} — пора пройти самопроверку)" if wk else ""
    return (f"Вы сейчас на программе «<b>{name}</b>»{where}.\n\n"
            "Одновременно идёт только одна программа. Продолжите текущую — или, если хотите "
            "начать другую, сначала завершите эту либо сбросьте прогресс «🔄 Начать заново».")


def week_intro(wi: dict) -> str:
    # §7.1 — четыре блока недели: вводный экран → смысл → цель → результат (+ ключевые темы)
    parts = [f"🗓 <b>Новая неделя: {wi['title']}</b>", "", wi.get("intro_screen", "").strip()]
    if wi.get("meaning"):
        parts += ["", f"🧩 <b>О чём эта неделя:</b> {wi['meaning'].strip()}"]
    if wi.get("goal"):
        parts += ["", f"🎯 <b>Цель недели:</b> {wi['goal'].strip()}"]
    if wi.get("result"):
        parts += ["", f"🌿 <b>К концу недели:</b> {wi['result'].strip()}"]
    themes = wi.get("key_themes") or []
    if themes:
        parts += ["", "Ключевые темы:"] + [f"• {t}" for t in themes]
    return "\n".join(p for p in parts if p is not None)


def path_history(completed: list[dict]) -> str:
    """Список пройденных программ для «Мой путь»."""
    lines = ["✅ <b>Пройденные программы:</b>"]
    for e in completed:
        lines.append(f"• {e.get('name', e.get('module', ''))}")
    return "\n".join(lines)


def path_status(s: dict) -> str:
    parts = [f"🧭 <b>Ваш путь</b>", "", f"Модуль: <b>{s['name']}</b>"]
    st = s["status"]
    if st == "completed":
        parts.append("🏁 Модуль пройден — все 6 недель позади.")
    elif st == "selfcheck_due":
        parts.append(f"Неделя {s['week']}/6 пройдена. Осталось подвести итоги недели.")
    else:
        parts.append(f"Неделя {s['week']}/{s['total_weeks']} · день {s['day']}/{s['total_days']}")
    if s.get("mode") == "test":
        parts.append("<i>(тест-режим)</i>")
    if s.get("days_total"):
        parts.append(f"Пройдено дней: <b>{s.get('days_completed', 0)}</b> из {s['days_total']}")
    weeks = s.get("weeks") or []
    if weeks:
        line = " ".join(f"{ZONE.get(w['zone'], '•')}{w['week']}" for w in weeks)
        parts += ["", f"Итоги недель: {line}"]
    return "\n".join(parts)


def _hhmm(slot: dict) -> str:
    return f"{slot['hour']:02d}:{slot['minute']:02d}"


def settings_view(s: dict) -> str:
    return ("⚙️ <b>Настройки напоминаний</b>\n\n"
            f"☀️ Утренний опрос: <b>{_hhmm(s['morning'])}</b>\n"
            f"🌤 Напоминание о задании: <b>{_hhmm(s['afternoon'])}</b>\n"
            f"🌙 Вечерний опрос: <b>{_hhmm(s['evening'])}</b>\n"
            f"🌍 Часовой пояс: <b>{s['timezone']}</b>\n\n"
            "Напоминания приходят каждый день в это время (если день ещё не пройден). "
            "Отключить их нельзя — можно только менять время. Меняйте кнопками ниже.")


_SLOT_NUDGE = {
    "morning": "☀️ Доброе утро! Сегодняшний день маршрута «{m}» ждёт вас — начните с «📅 Сегодня», когда будет минутка.",
    "afternoon": "🌤 Напоминание про задание дня в маршруте «{m}». Если ещё не проходили — загляните в «📅 Сегодня».",
    "evening": "🌙 Вечер — спокойное время подвести день. День маршрута «{m}» ещё открыт: «📅 Сегодня».",
}


def reminder_nudge(item: dict) -> str:
    tpl = _SLOT_NUDGE.get(item.get("slot"), _SLOT_NUDGE["evening"])
    return tpl.format(m=item.get("module_name", ""))


def _date_disp(iso: str) -> str:
    """'2026-07-15T..' → '15.07.2026'."""
    d = (iso or "")[:10]
    parts = d.split("-")
    return f"{parts[2]}.{parts[1]}.{parts[0]}" if len(parts) == 3 else d


def journal_index(total: int) -> str:
    if total == 0:
        return ("📔 <b>Мой дневник</b>\n\nПока пусто. Сюда попадают ваши ежедневные рефлексии "
                "и личные заметки.\n\nМожно добавить первую заметку кнопкой ниже.")
    return (f"📔 <b>Мой дневник</b>\n\nВсего записей: {total}.\n"
            "Выберите день, чтобы посмотреть записи, или добавьте заметку.")


def journal_day(disp: str, entries: list[dict]) -> str:
    head = f"📔 <b>{disp}</b>\n"
    blocks = []
    for e in entries:
        label = SOURCE_LABEL.get(e["source_type"], e["source_type"])
        loc = f" · Н{e['week']}Д{e['day']}" if e.get("week") and e.get("day") else ""
        blocks.append(f"\n{label}{loc}\n{e['text']}")
    return head + "\n".join(blocks)


def selfcheck_result(r: dict) -> str:
    z = ZONE.get(r["zone"], "•")
    parts = [f"{z} Итоги недели", "", r["user_text"], "", f"➡️ {r['recommendation']}"]
    for t in r.get("critical_texts", []):
        parts += ["", t]
    nxt = r.get("next", {})
    if nxt.get("status") == "completed":
        parts += ["", "🏁 Модуль завершён."]
    elif nxt.get("week"):
        parts += ["", f"Открыта неделя {nxt['week']}."]
    return "\n".join(parts)


def _pm_line(item: dict) -> str:
    """Одна строка смежной темы: готовый модуль назван программой, иначе — тема + пометка."""
    nm = item.get("module_name")
    if nm:
        return f"• «<b>{nm}</b>» — эту программу можно начать в любой момент."
    topic = item.get("topic_name") or "эта тема"
    return f"• <b>{topic}</b> — направление в подготовке, пока доступно как ориентир."


def postmodule_result(r: dict) -> str:
    """Пользовательский текст постмодуля — без баллов и тегов; готовый модуль зовём программой,
    тему без модуля — по имени с пометкой «готовится» (§16)."""
    kind = r.get("kind")
    head = "🧭 <b>Смежные направления</b>"
    tail = ("\n\n<i>Это не обязательный переход и не оценка пройденного. "
            "Вы можете взять паузу на закрепление или выбрать новое направление, когда захотите.</i>")

    if kind == "test":
        recs = r.get("recommended", [])
        if not recs:
            return (f"{head}\n\nПо вашим ответам сейчас нет ярко выраженной смежной темы. "
                    "Это хороший знак — можно спокойно закрепить пройденное." + tail)
        body = "\n".join(_pm_line(x) for x in recs)
        return f"{head}\n\nПо вашим ответам сейчас ближе всего:\n{body}{tail}"

    if kind == "flags":
        focuses = r.get("focuses", [])
        if not focuses:
            return (f"{head}\n\nЗа время модуля не накопилось выраженных смежных тем. "
                    "Можно спокойно закрепить пройденное." + tail)
        lines = []
        for f in focuses:
            line = _pm_line(f)
            if f.get("text"):
                line += f"\n  {f['text']}"
            lines.append(line)
        return f"{head}\n\n" + "\n".join(lines) + tail

    return f"{head}\n\nДля этой программы смежные направления не предусмотрены."


def _clip(s: str, n: int = 220) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def test_transcript(r: dict) -> list[str]:
    """Читаемый дамп прогона для тестировщика. Возвращает список сообщений (учёт лимита Telegram)."""
    msgs, buf = [], []
    def flush():
        if buf:
            msgs.append("\n".join(buf)); buf.clear()

    buf.append(f"🧪 Прогон: scope=<b>{r['scope']}</b>, пресет=<b>{r['preset']}</b>")
    for s in r["steps"]:
        if s["event"] == "day":
            buf.append(f"\n<b>W{s['week']}D{s['day']} · {s['day_title']}</b>")
            buf.append(f"Фокус: {_clip(s['focus'])}")
            q = s.get("quiz") or {}
            if q.get("question"):
                buf.append(f"Квиз: {q['question']} [{len(q.get('options', []))} вар.]")
        elif s["event"] == "selfcheck":
            z = ZONE.get(s["zone"], "•")
            buf.append(f"\n{z} Самопроверка W{s['week']}: зона {s['zone']} (score {s['core_score']})")
            buf.append(f"➡️ {_clip(s['recommendation'], 160)}")
            if s.get("critical_texts"):
                buf.append(f"⚠️ critical-блоков: {len(s['critical_texts'])}")
        elif s["event"] == "module_completed":
            buf.append("\n🏁 Модуль завершён")
        if sum(len(x) for x in buf) > 3200:
            flush()
    pm = r.get("postmodule")
    if pm:
        if pm["kind"] == "test":
            rec = ", ".join(f"{x['tag']}({x['score']})" for x in pm.get("recommended", []))
            buf.append(f"\n📊 Постмодуль (тест): рекомендовано — {rec or '—'}")
        elif pm["kind"] == "flags":
            foc = ", ".join(f"{f['tag']}" for f in pm.get("focuses", []))
            buf.append(f"\n📊 Постмодуль (флаги): смежные фокусы — {foc or '—'}")
    flush()
    return msgs
