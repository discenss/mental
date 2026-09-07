"""Сборка последовательности шагов дня — единый источник истины для всех каналов.

Раньше `day_steps` строил только Telegram-бот (`bot/handlers/flow.py`), а `/today`
отдавал сырой день. Второй клиент (iOS) означал бы вторую реализацию прохождения дня
и неизбежное расхождение. Поэтому последовательность собирается здесь, а каналы её
только рендерят.

Формат шага — структурный, плюс готовый текст для Telegram:

    {kind, ...поля шага..., text?}

`kind` и структурные поля (`focus`, `task`, `options`, `prompt`, …) — то, из чего
клиент строит свой UI. `text` — предрендеренная HTML-строка ровно того вида, что бот
показывал раньше; он берёт её как есть, iOS её игнорирует и верстает по полям. Так
переход бота на этот эндпоинт не меняет ни одной его формулировки.

Виды шагов (порядок = порядок прохождения):
  morning:  info(intent)* → focustask → audio?
  evening:  focustask → quiz? → free_text × 3
"""
from __future__ import annotations


def _task_text(task: dict) -> str:
    """Текст задания + подзадачи списком (как в боте)."""
    text = task.get("text") or ""
    subtasks = task.get("subtasks") or []
    return text + "".join(f"\n• {s}" for s in subtasks)


def _morning(today: dict) -> list[dict]:
    steps: list[dict] = []
    for q in today.get("intent_questions") or []:                   # W6-спец
        steps.append({"kind": "info", "role": "intent", "question": q,
                      "text": f"🎯 {q}"})
    task = today.get("task") or {}
    steps.append({
        "kind": "focustask", "role": "morning",
        "focus": today.get("focus"),
        "task": {"text": task.get("text"), "subtasks": task.get("subtasks") or []},
        # в утренней сессии задание только показывается, статус спрашивают вечером
        "asks_status": False,
        "text": (f"📌 <b>Фокус дня</b>\n{today.get('focus')}\n\n"
                 f"📝 <b>Задание дня</b>\n{_task_text(task)}"
                 "\n\n<i>Занимайтесь днём, а вечером вернитесь закрыть день.</i>"),
    })
    audio = today.get("audio")
    if audio:
        steps.append({"kind": "audio", "code": audio.get("code"),
                      "title": audio.get("title")})
    return steps


def _evening(today: dict) -> list[dict]:
    steps: list[dict] = []
    task = today.get("task") or {}
    steps.append({
        "kind": "focustask", "role": "evening",
        "focus": today.get("focus"),
        "task": {"text": task.get("text"), "subtasks": task.get("subtasks") or []},
        # вечером тот же блок задания, но с вопросом о статусе DONE|PARTIAL|NOT_DONE
        "asks_status": True,
        "status_options": ["DONE", "PARTIAL", "NOT_DONE"],
        "text": (f"📝 <b>Задание дня</b>\n{_task_text(task)}\n\nКак прошло сегодня?"),
    })
    quiz = today.get("quiz") or {}
    if quiz.get("question"):
        steps.append({"kind": "quiz", "question": quiz["question"],
                      "options": quiz.get("options") or [],
                      "text": quiz["question"]})
    for q in today.get("reflection") or []:
        steps.append({"kind": "free_text", "prompt": q, "text": q})
    return steps


def build(today: dict) -> dict:
    """Сырой день (`progression.get_today`) → день + готовые шаги.

    Нетерминальные статусы (`completed`, `selfcheck_due`) шагов не имеют: там канал
    показывает свой экран, а не проход по дню. Возвращаем их как есть, со пустым
    `steps`, чтобы клиенту хватило одного запроса и одной ветки по `status`.
    """
    status = today.get("status")
    if status != "active":
        return {**today, "steps": [], "session": None}

    session = today.get("session", "morning")
    steps = _morning(today) if session == "morning" else _evening(today)
    return {**today, "steps": steps}
