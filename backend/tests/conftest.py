"""Изоляция тестов от рабочей БД: каждый прогон — свежая SQLite-копия схемы + контент."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ВАЖНО: до импорта app.* — иначе Settings успеет прочитать боевой DATABASE_URL
_tmpdir = tempfile.mkdtemp(prefix="mental-tests-")
_dbfile = Path(_tmpdir) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_dbfile}"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app.database import engine
    from app import models as m
    m.Base.metadata.create_all(engine)
    # контент нужен для /enroll и /today: грузим те же YAML, что боевой скрипт
    from pathlib import Path as _Path
    from app.config import settings
    from app.content_loader import load_intake, load_module
    from app.database import SessionLocal
    content = _Path(settings.content_dir)
    with SessionLocal() as db:
        try:
            for f in sorted((content / "modules").glob("*.yaml")):
                load_module(db, f)
            intake = content / "intake.yaml"
            if intake.exists():
                load_intake(db, intake)
        except Exception as e:                              # noqa: BLE001
            pytest.skip(f"не удалось загрузить контент для тестов: {e}")
    yield
