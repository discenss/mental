#!/bin/sh
# Миграции + загрузка контента (идемпотентно), затем запуск переданной команды (uvicorn).
set -e

echo "[entrypoint] alembic upgrade head…"
alembic upgrade head

echo "[entrypoint] загрузка контента (intake + модули)…"
python -m scripts.load_content

echo "[entrypoint] старт: $*"
exec "$@"
