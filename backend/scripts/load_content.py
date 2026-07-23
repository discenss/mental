"""Загрузить весь контент в БД и вывести отчёт-проверку.

Запуск:  python -m scripts.load_content
Схему создаёт Alembic (`alembic upgrade head`); create_all здесь — безопасный фолбэк
для отсутствующих таблиц (idempotent), чтобы скрипт работал и standalone.
"""
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal, engine
from app import models as m
from app.content_loader import (load_module, load_intake,
                                load_module_translation, load_intake_translation)

CONTENT = Path(settings.content_dir)


def main() -> None:
    m.Base.metadata.create_all(engine)  # фолбэк; после alembic upgrade — no-op

    with SessionLocal() as db:
        # модули (ru — основной язык, base-таблицы)
        module_files = sorted((CONTENT / "modules").glob("*.yaml"))
        for f in module_files:
            code = load_module(db, f)
            print(f"✓ модуль загружен: {code}  ({f.name})")

        # интейк (после модулей — чтобы привязать направления к загруженным модулям)
        intake_file = CONTENT / "intake.yaml"
        if intake_file.exists():
            n = load_intake(db, intake_file)
            print(f"✓ интейк загружен: {n} вопросов  ({intake_file.name})")

        # переводы модулей (§ многоязычность) — content/modules/translations/{code}.{lang}.yaml
        translations_dir = CONTENT / "modules" / "translations"
        for f in sorted(translations_dir.glob("*.yaml")) if translations_dir.is_dir() else []:
            ref = load_module_translation(db, f)
            print(f"✓ перевод модуля загружен: {ref}  ({f.name})")

        # переводы интейка — content/intake_translations/{lang}.yaml
        intake_tr_dir = CONTENT / "intake_translations"
        for f in sorted(intake_tr_dir.glob("*.yaml")) if intake_tr_dir.is_dir() else []:
            lang = load_intake_translation(db, f)
            print(f"✓ перевод интейка загружен: {lang}  ({f.name})")

        print("\n=== ОТЧЁТ ИЗ БД ===")
        c = lambda model: db.scalar(select(func.count()).select_from(model))
        print(f"modules:            {c(m.Module)}")
        print(f"module_weeks:       {c(m.ModuleWeek)}")
        print(f"module_days:        {c(m.ModuleDay)}")
        print(f"markers:            {c(m.Marker)}")
        print(f"audio_assets:       {c(m.AudioAsset)}")
        print(f"selfcheck_questions:{c(m.SelfcheckQuestion)}")
        print(f"zone_interps:       {c(m.ZoneInterp)}")
        print(f"critical_triggers:  {c(m.CriticalTrigger)}")
        print(f"intake_directions:  {c(m.IntakeDirection)}")
        print(f"intake_questions:   {c(m.IntakeQuestion)}")
        print(f"intake_interps:     {c(m.IntakeInterp)}")

        translation_models = [
            m.ModuleTranslation, m.ModuleWeekTranslation, m.ModuleDayTranslation,
            m.MarkerTranslation, m.SelfcheckQuestionTranslation, m.ZoneInterpTranslation,
            m.CriticalTriggerTranslation, m.FinalProductTemplateTranslation,
            m.PostmoduleConfigTranslation, m.IntakeConfigTranslation,
            m.IntakeDirectionTranslation, m.IntakeQuestionTranslation,
            m.IntakeInterpTranslation, m.IntakeStaticTextTranslation,
        ]
        total_translations = sum(c(model) for model in translation_models)
        if total_translations:
            print(f"\n=== ПЕРЕВОДЫ ({total_translations} строк) ===")
            for model in translation_models:
                n = c(model)
                if n:
                    print(f"  {model.__tablename__}: {n}")

        # выборочная проверка целостности одного модуля
        for (code,) in db.execute(select(m.Module.code)).all():
            weeks = db.scalar(select(func.count()).select_from(m.ModuleWeek).where(m.ModuleWeek.module_code == code))
            audio = db.scalar(select(func.count()).select_from(m.AudioAsset).where(m.AudioAsset.module_code == code))
            week_ids = [wid for (wid,) in db.execute(select(m.ModuleWeek.id).where(m.ModuleWeek.module_code == code)).all()]
            days = db.scalar(select(func.count()).select_from(m.ModuleDay).where(m.ModuleDay.week_id.in_(week_ids)))
            print(f"  [{code}] недель={weeks} дней={days} аудио={audio}")

        # проверка ключевого инварианта интейка: направление BOUND → модуль bound
        bound_dir = db.get(m.IntakeDirection, "BOUND")
        if bound_dir:
            print(f"  intake: направление BOUND → модуль '{bound_dir.module_code}'")


if __name__ == "__main__":
    main()
