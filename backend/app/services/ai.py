"""ИИ-слой Mental Club — та же схема, что в rhythmos.

- Провайдер openai | anthropic (переключается конфигом).
- Два тира моделей: everyday (будни, дешёвая) и analytics (итоги/инсайты, сильная).
- Guardrails по нормативу §16: без диагнозов/лечения/оценок, спокойный взрослый тон,
  безопасная эскалация при признаках кризиса.
- При отсутствии ключа (llm_enabled=False) — мягкий graceful-ответ, без падений.

Распознавание аудио (Whisper) — на стороне клиента (bot/voice.py), тем же ключом.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app import models as m

logger = logging.getLogger(__name__)

try:
    import openai
    _OPENAI = True
except ImportError:
    _OPENAI = False
try:
    import anthropic
    _ANTHROPIC = True
except ImportError:
    _ANTHROPIC = False


EVERYDAY_SYSTEM = (
    "Ты — спокойный поддерживающий помощник Mental Club. Отвечай коротко, по-взрослому, "
    "уважительно, на языке пользователя (по умолчанию русский). Ты НЕ ставишь диагнозов, "
    "не назначаешь лечение, не обещаешь результат и не используешь слова «диагноз», «патология», "
    "«клиент», «пациент». Помогаешь заметить состояние, мягко переформулировать и предложить один "
    "маленький посильный шаг. Если в сообщении есть признаки кризиса, насилия или угрозы жизни — "
    "мягко порекомендуй обратиться за профессиональной поддержкой и не давай инструкций по действиям."
)

ANALYTICS_SYSTEM = (
    "Ты — аналитик Mental Club. По данным прохождения модуля (зоны недельных самопроверок, ответы "
    "рефлексий, записи дневника, финальный продукт) собери короткий поддерживающий итог: что человек "
    "начал замечать, что уже даётся, что может удерживать, куда бережно двигаться дальше. Тон спокойный, "
    "без диагнозов, без оценок «хорошо/плохо», без обещаний. 3–5 коротких абзацев, на языке данных."
)


WEEK_SYSTEM = (
    "Ты — тёплый аналитик Mental Club. По итогам ОДНОЙ недели (зона недельной самопроверки и "
    "фрагменты рефлексий за эту неделю) дай короткий поддерживающий отклик: что человек за неделю "
    "начал замечать, что уже даётся, на что мягко обратить внимание дальше. Без диагнозов, без "
    "оценок «хорошо/плохо», без обещаний. 2–3 коротких абзаца, на языке данных, по-взрослому."
)


def _model(tier: str) -> str:
    if settings.llm_provider == "openai":
        return settings.everyday_openai_model if tier == "everyday" else settings.analytics_openai_model
    return settings.everyday_anthropic_model if tier == "everyday" else settings.analytics_anthropic_model


def _chat(system: str, user: str, tier: str) -> str:
    """Один вызов LLM с ретраями. Возвращает текст."""
    model = _model(tier)
    last_err = None
    for attempt in range(settings.llm_max_retries + 1):
        try:
            if settings.llm_provider == "openai":
                if not _OPENAI:
                    raise RuntimeError("openai не установлен")
                client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout)
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                return (r.choices[0].message.content or "").strip()
            else:
                if not _ANTHROPIC:
                    raise RuntimeError("anthropic не установлен")
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                r = client.messages.create(
                    model=model, max_tokens=1024, system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        except Exception as e:                          # noqa: BLE001 — ретраим любые
            last_err = e
            logger.warning("LLM попытка %d не удалась: %s", attempt + 1, type(e).__name__)
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"LLM недоступен: {last_err}")


# ── будни: свободный вопрос пользователя ──────────────────────────────────────

def ask(question: str, *, context: str | None = None) -> dict:
    if not settings.llm_enabled:
        return {"enabled": False,
                "text": "ИИ-помощник пока не подключён. Обратитесь к своему сопровождающему или "
                        "попробуйте позже."}
    user = question if not context else f"Контекст: {context}\n\nВопрос: {question}"
    return {"enabled": True, "text": _chat(EVERYDAY_SYSTEM, user, tier="everyday")}


# ── аналитика: итог модуля по данным пользователя ─────────────────────────────

def week_insight(db: Session, enrollment: m.Enrollment) -> dict:
    """ИИ-разбор последней пройденной недели (зона + рефлексии этой недели)."""
    if not settings.llm_enabled:
        return {"enabled": False, "text": "Разбор недели станет доступен, когда подключён ИИ."}
    latest = db.execute(
        select(m.SelfcheckResult).where(m.SelfcheckResult.enrollment_id == enrollment.id)
        .order_by(m.SelfcheckResult.week_n.desc())
    ).scalars().first()
    if latest is None:
        return {"enabled": True, "text": "По этой неделе пока нет данных самопроверки."}
    wk = latest.week_n
    refl = db.execute(
        select(m.DailyEntry.reflection_answers)
        .where(m.DailyEntry.enrollment_id == enrollment.id, m.DailyEntry.week_n == wk)
        .order_by(m.DailyEntry.day_n)
    ).all()
    refl_texts = [t for (arr,) in refl for t in (arr or []) if t and t.strip()][:12]
    lines = [f"Неделя {wk}. Зона недельной самопроверки: {latest.zone}."]
    if refl_texts:
        lines.append("Фрагменты рефлексий недели:\n- " + "\n- ".join(refl_texts))
    return {"enabled": True, "text": _chat(WEEK_SYSTEM, "\n".join(lines), tier="analytics")}


def module_insight(db: Session, enrollment: m.Enrollment) -> dict:
    if not settings.llm_enabled:
        return {"enabled": False, "text": "Аналитика по модулю станет доступна, когда подключён ИИ."}

    zones = db.execute(
        select(m.SelfcheckResult.week_n, m.SelfcheckResult.zone)
        .where(m.SelfcheckResult.enrollment_id == enrollment.id)
        .order_by(m.SelfcheckResult.week_n)
    ).all()
    refl = db.execute(
        select(m.DailyEntry.week_n, m.DailyEntry.reflection_answers)
        .where(m.DailyEntry.enrollment_id == enrollment.id)
        .order_by(m.DailyEntry.week_n, m.DailyEntry.day_n)
    ).all()
    fp = db.execute(
        select(m.FinalProductInstance.saved_content)
        .where(m.FinalProductInstance.enrollment_id == enrollment.id)
    ).scalar_one_or_none()

    lines = [f"Модуль: {enrollment.module_code}"]
    if zones:
        lines.append("Зоны самопроверок по неделям: " +
                     ", ".join(f"W{w}:{z}" for w, z in zones))
    refl_texts = [t for _, arr in refl for t in (arr or []) if t and t.strip()][:12]
    if refl_texts:
        lines.append("Фрагменты рефлексий:\n- " + "\n- ".join(refl_texts))
    if fp:
        lines.append(f"Финальный продукт: {fp}")
    context = "\n".join(lines)

    return {"enabled": True, "text": _chat(ANALYTICS_SYSTEM, context, tier="analytics")}
