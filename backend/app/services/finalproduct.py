"""Финальный личный продукт модуля (§14): протокол/ориентир, который пользователь
собирает из своих ответов и сохраняет.

Хранение:
  • FinalProductInstance.saved_content — источник правды (структура секция → ответ);
    отсюда рендерится и текст, и .md-файл, и его видит ИИ-итог.
  • «Мой дневник» — только КОРОТКАЯ отсылка (source_type='final_product', §12.1):
    «в Личных достижениях появился итог модуля …». Полный текст живёт в достижениях.
Идемпотентно: повторный сбор перезаписывает и instance, и дневниковую отсылку.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.services import i18n


def _module_name(db: Session, code: str, language: str = i18n.DEFAULT_LANGUAGE) -> str:
    mod = db.get(m.Module, code)
    if mod is None:
        return code
    return i18n.overlay(db, m.ModuleTranslation, m.ModuleTranslation.module_code, code,
                        language, mod, ["name"])["name"]


def _template_view(db: Session, module_code: str,
                   language: str) -> tuple[m.FinalProductTemplate | None, dict | None]:
    tpl = db.get(m.FinalProductTemplate, module_code)
    if tpl is None:
        return None, None
    view = i18n.overlay(db, m.FinalProductTemplateTranslation, m.FinalProductTemplateTranslation.module_code,
                        module_code, language, tpl, ["title", "sections"])
    return tpl, view


def get_template(db: Session, enrollment: m.Enrollment) -> dict:
    """Шаблон продукта для показа: заголовок + секции (тексты-подсказки)."""
    language = i18n.resolve_language(enrollment.user)
    tpl, view = _template_view(db, enrollment.module_code, language)
    if tpl is None:
        return {"exists": False, "title": None, "sections": []}
    return {"exists": True, "title": view["title"], "sections": list(view["sections"])}


def _render_text(title: str, sections: list[str], answers: list[str]) -> str:
    """Собрать человекочитаемый текст продукта для дневника."""
    lines = [title, ""]
    for i, sec in enumerate(sections):
        head = sec.strip().split("\n", 1)[0]                 # первая строка секции — заголовок
        ans = answers[i].strip() if i < len(answers) and isinstance(answers[i], str) else ""
        lines.append(head)
        lines.append(ans if ans else "—")
        lines.append("")
    return "\n".join(lines).strip()


def save(db: Session, enrollment: m.Enrollment, answers: list[str]) -> dict:
    """Сохранить собранный продукт: instance + запись в дневник. Идемпотентно.

    saved_content — снимок на момент сохранения, в языке пользователя на тот момент
    (как исторический факт, аналогично AudioVariant.channel_cache — задним числом не меняется)."""
    language = i18n.resolve_language(enrollment.user)
    tpl, view = _template_view(db, enrollment.module_code, language)
    if tpl is None:
        raise ValueError("у модуля нет шаблона финального продукта")
    title, sections = view["title"], list(view["sections"])
    answers = [a if isinstance(a, str) else "" for a in (answers or [])]

    saved_content = {"title": title,
                     "items": [{"section": sections[i], "answer": (answers[i] if i < len(answers) else "")}
                               for i in range(len(sections))]}

    # instance — перезаписываем прежний для этого enrollment
    db.execute(m.FinalProductInstance.__table__.delete().where(
        m.FinalProductInstance.enrollment_id == enrollment.id))
    db.add(m.FinalProductInstance(enrollment_id=enrollment.id, saved_content=saved_content))

    # дневник — КОРОТКАЯ отсылка (полный текст живёт в «Личных достижениях»)
    db.execute(m.JournalEntry.__table__.delete().where(
        m.JournalEntry.user_id == enrollment.user_id,
        m.JournalEntry.module_code == enrollment.module_code,
        m.JournalEntry.source_type == "final_product",
    ))
    mod_name = _module_name(db, enrollment.module_code, language)
    ref = f"🏆 В «Личных достижениях» появился ваш итог модуля «{mod_name}» — {title}."
    db.add(m.JournalEntry(
        user_id=enrollment.user_id, source_type="final_product",
        module_code=enrollment.module_code, week_n=None, day_n=None, text=ref,
    ))
    db.commit()
    text = _render_text(title, sections, answers)
    return {"ok": True, "title": title, "text": text, "journal_ref": ref}


def list_for_user(db: Session, user_id: int) -> list[dict]:
    """Все собранные продукты пользователя (для экрана «Личные достижения»)."""
    language = i18n.resolve_language(db.get(m.User, user_id))
    rows = db.execute(
        select(m.FinalProductInstance, m.Enrollment)
        .join(m.Enrollment, m.FinalProductInstance.enrollment_id == m.Enrollment.id)
        .where(m.Enrollment.user_id == user_id)
        .order_by(m.FinalProductInstance.id.desc())
    ).all()
    out = []
    for inst, enr in rows:
        sc = inst.saved_content or {}
        out.append({
            "enrollment_id": enr.id, "module_code": enr.module_code,
            "module_name": _module_name(db, enr.module_code, language),
            "title": sc.get("title", ""),
            "text": _render_from_content(sc),
        })
    return out


def get_for_enrollment(db: Session, enrollment: m.Enrollment) -> dict | None:
    inst = db.execute(select(m.FinalProductInstance).where(
        m.FinalProductInstance.enrollment_id == enrollment.id)).scalar_one_or_none()
    if inst is None:
        return None
    language = i18n.resolve_language(enrollment.user)
    sc = inst.saved_content or {}
    return {"title": sc.get("title", ""), "module_code": enrollment.module_code,
            "module_name": _module_name(db, enrollment.module_code, language),
            "text": _render_from_content(sc), "md": render_md(db, enrollment, sc, language)}


def _render_from_content(sc: dict) -> str:
    """Человекочитаемый текст из saved_content (источник правды)."""
    title = sc.get("title", "")
    lines = [title, ""]
    for it in sc.get("items", []):
        head = (it.get("section") or "").strip().split("\n", 1)[0]
        ans = (it.get("answer") or "").strip()
        lines.append(head)
        lines.append(ans if ans else "—")
        lines.append("")
    return "\n".join(lines).strip()


def render_md(db: Session, enrollment: m.Enrollment, sc: dict,
             language: str = i18n.DEFAULT_LANGUAGE) -> str:
    """Markdown-версия продукта для скачивания файлом."""
    title = sc.get("title", "")
    mod = _module_name(db, enrollment.module_code, language)
    lines = [f"# {title}", "", f"*Модуль: {mod}*", ""]
    for it in sc.get("items", []):
        head = (it.get("section") or "").strip().split("\n", 1)[0]
        ans = (it.get("answer") or "").strip()
        lines.append(f"## {head}")
        lines.append(ans if ans else "_(не заполнено)_")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
