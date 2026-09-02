#!/usr/bin/env bash
# Деплой/обновление Mental Club. Запускать в каталоге проекта (напр. ~/mental или /srv/mental).
#
# Первый раз: скопируй .env.example→.env, backend/.env.prod.example→backend/.env.prod,
# bot/.env.prod.example→bot/.env.prod и заполни секреты. Затем ./deploy.sh
#
# Что делает: git pull → сборка образов → пересоздание backend и bot → ожидание healthy.
# БД (mental-db) НЕ трогается: её пересоздание при обновлении кода не нужно и рискованно.
#
# Флаги:
#   --no-pull      не делать git pull (деплой того, что уже лежит в рабочем каталоге)
#   --no-backup    не снимать дамп БД перед деплоем
#   --service X    пересоздать только backend | bot (по умолчанию оба)
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=lib-compose.sh
source ./lib-compose.sh

DO_PULL=1; DO_BACKUP=1; ONLY_SERVICE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)    DO_PULL=0 ;;
    --no-backup)  DO_BACKUP=0 ;;
    --service)    ONLY_SERVICE="${2:-}"; shift ;;
    -h|--help)    sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "неизвестный флаг: $1" >&2; exit 2 ;;
  esac
  shift
done

detect_compose
echo "→ compose: $COMPOSE_KIND"

echo "→ проверка .env-файлов"
for f in .env backend/.env.prod bot/.env.prod; do
  [ -f "$f" ] || { echo "  ОТСУТСТВУЕТ $f — скопируй из *.example и заполни"; exit 1; }
done

if [ "$DO_PULL" = 1 ]; then
  echo "→ git pull"
  if [ -d .git ]; then
    # незакоммиченные правки на проде — повод остановиться, а не молча их потерять
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "✖ в рабочем каталоге есть незакоммиченные изменения:" >&2
      git status --short >&2
      echo "  закоммить/откати их или запусти с --no-pull" >&2
      exit 1
    fi
    git pull --ff-only origin main
  else
    echo "  (пропущено: не git-репозиторий)"
  fi
fi

# Дамп БД до деплоя: миграции применяются автоматически на старте backend
# (docker-entrypoint.sh → alembic upgrade head), а откатить их нечем.
if [ "$DO_BACKUP" = 1 ] && docker ps --format '{{.Names}}' | grep -qx "$(container_of db)"; then
  echo "→ бэкап БД перед деплоем"
  ./backup.sh --quiet || { echo "✖ бэкап не удался — деплой остановлен" >&2; exit 1; }
fi

SERVICES=(backend bot)
[ -n "$ONLY_SERVICE" ] && SERVICES=("$ONLY_SERVICE")

echo "→ сборка образов: ${SERVICES[*]}"
compose build "${SERVICES[@]}"

echo "→ поднимаем БД (если не запущена)"
compose up -d db

# Пересоздаём по одному сервису, а не «compose up» по всему стеку:
#  — на v1 «up» поверх существующего контейнера падает на ContainerConfig и оставляет сервис лежащим;
#  — по одному видно, ЧТО именно не поднялось, и остальные сервисы не задеты.
for svc in "${SERVICES[@]}"; do
  echo "→ пересоздаём $svc"
  compose up -d --no-deps --force-recreate "$svc" || {
    echo "✖ не удалось пересоздать $svc (compose $COMPOSE_KIND)" >&2
    echo "  логи: docker logs --tail 50 $(container_of "$svc")" >&2
    exit 1
  }
done

# Ждём healthy: без этого скрипт «успешно» завершается на упавшем сервисе
# (контейнер создан ≠ приложение работает).
echo "→ ждём готовности"
for svc in "${SERVICES[@]}"; do
  name="$(container_of "$svc")"
  for _ in $(seq 1 60); do
    state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo none)"
    [ "$state" = "running" ] && { [ "$health" = "healthy" ] || [ "$health" = "none" ]; } && break
    if [ "$state" = "exited" ] || [ "$state" = "missing" ]; then
      echo "✖ $name: $state" >&2
      docker logs --tail 40 "$name" 2>&1 >&2 || true
      exit 1
    fi
    sleep 2
  done
  state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo none)"
  if [ "$state" != "running" ] || { [ "$health" != "healthy" ] && [ "$health" != "none" ]; }; then
    echo "✖ $name не стал healthy за 120с (status=$state health=$health)" >&2
    docker logs --tail 40 "$name" 2>&1 >&2 || true
    exit 1
  fi
  echo "  ✓ $name ($health)"
done

echo "→ статус"
compose ps
echo "готово ($(git rev-parse --short HEAD 2>/dev/null || echo '?')). Логи: docker logs -f $(container_of backend)"
