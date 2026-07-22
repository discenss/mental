#!/usr/bin/env bash
# Деплой/обновление Mental Club на сервере. Запускать в каталоге проекта (напр. /srv/mental).
# Первый раз: скопируй .env.example→.env, backend/.env.prod.example→backend/.env.prod,
# bot/.env.prod.example→bot/.env.prod и заполни секреты. Затем ./deploy.sh
set -euo pipefail

COMPOSE="docker-compose -f docker-compose.prod.yml"

echo "→ git pull"
git pull origin main || echo "  (пропущено: не git-репозиторий или нет remote)"

echo "→ проверка .env-файлов"
for f in .env backend/.env.prod bot/.env.prod; do
  [ -f "$f" ] || { echo "  ОТСУТСТВУЕТ $f — скопируй из *.example и заполни"; exit 1; }
done

echo "→ сборка и запуск (db → backend → bot)"
$COMPOSE up -d --build

echo "→ статус"
$COMPOSE ps
echo "готово. Логи: $COMPOSE logs -f backend | bot"
