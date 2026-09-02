#!/usr/bin/env bash
# Налить дамп в БД Mental Club. Используется при переезде на новый сервер и для отката.
#
#   ./restore.sh backups/mental-20260902-120000.sql.gz
#   ./restore.sh --latest
#
# ВНИМАНИЕ: перезаписывает содержимое БД (дамп снят с --clean --if-exists).
# Перед наливкой скрипт сам делает страховочный дамп текущего состояния.
#
# Флаги:
#   --latest       взять самый свежий файл из ./backups
#   --yes          не спрашивать подтверждение (для автоматизации)
#   --no-safety    не делать страховочный дамп текущей БД
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=lib-compose.sh
source ./lib-compose.sh

DUMP=""; USE_LATEST=0; ASSUME_YES=0; SAFETY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --latest)    USE_LATEST=1 ;;
    --yes|-y)    ASSUME_YES=1 ;;
    --no-safety) SAFETY=0 ;;
    -h|--help)   sed -n '2,16p' "$0"; exit 0 ;;
    -*) echo "неизвестный флаг: $1" >&2; exit 2 ;;
    *)  DUMP="$1" ;;
  esac
  shift
done

if [ "$USE_LATEST" = 1 ]; then
  DUMP="$(ls -1t ./backups/mental-*.sql.gz 2>/dev/null | head -1 || true)"
  [ -n "$DUMP" ] || { echo "✖ в ./backups нет дампов" >&2; exit 1; }
fi
[ -n "$DUMP" ] || { echo "укажи файл дампа или --latest (см. --help)" >&2; exit 2; }
[ -f "$DUMP" ] || { echo "✖ файл не найден: $DUMP" >&2; exit 1; }
gzip -t "$DUMP" 2>/dev/null || { echo "✖ дамп повреждён: $DUMP" >&2; exit 1; }

detect_compose

[ -f .env ] && set -a && . ./.env && set +a
DB_USER="${DB_USER:-mental}"
DB_NAME="${DB_NAME:-mental}"
DB_CONTAINER="$(container_of db)"

echo "→ поднимаем БД (если не запущена)"
compose up -d db
for _ in $(seq 1 60); do
  docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" >/dev/null 2>&1 && break
  sleep 2
done
docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" >/dev/null 2>&1 || {
  echo "✖ $DB_CONTAINER не готов" >&2; exit 1; }

if [ "$ASSUME_YES" != 1 ]; then
  echo
  echo "Восстановление ПЕРЕЗАПИШЕТ базу '$DB_NAME' в $DB_CONTAINER."
  echo "  дамп: $DUMP ($(du -h "$DUMP" | cut -f1))"
  printf "Продолжить? [y/N] "
  read -r ans
  case "$ans" in y|Y|yes) ;; *) echo "отменено"; exit 0 ;; esac
fi

# Страховка: текущее состояние — до того, как его затрут
if [ "$SAFETY" = 1 ]; then
  echo "→ страховочный дамп текущей БД"
  ./backup.sh --quiet --out ./backups/pre-restore >/dev/null || {
    echo "✖ страховочный дамп не удался — восстановление остановлено" >&2
    echo "  (пропустить: --no-safety)" >&2
    exit 1; }
fi

# Бот и backend держат открытые соединения и могут писать во время наливки —
# останавливаем их, иначе получим гонку и частично восстановленную БД.
echo "→ останавливаем backend и bot на время наливки"
STOPPED=()          # порядок остановки: сначала bot, потом backend
for svc in bot backend; do
  name="$(container_of "$svc")"
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    docker stop "$name" >/dev/null && STOPPED+=("$svc")
  fi
done

restore_rc=0
echo "→ наливаем дамп"
gunzip -c "$DUMP" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 --quiet || restore_rc=$?

# Поднимаем обратно в обратном порядке (backend раньше bot: бот ходит в API).
# Проверяем длину явно: "${arr[@]:-}" на пустом массиве даёт одну пустую итерацию.
if [ "${#STOPPED[@]}" -gt 0 ]; then
  echo "→ поднимаем обратно: ${STOPPED[*]}"
  for (( i=${#STOPPED[@]}-1; i>=0; i-- )); do
    compose up -d --no-deps "${STOPPED[i]}" >/dev/null
  done
else
  echo "→ поднимать нечего (backend/bot не были запущены)"
fi

if [ "$restore_rc" != 0 ]; then
  echo "✖ наливка завершилась с ошибкой (код $restore_rc)" >&2
  [ "$SAFETY" = 1 ] && echo "  прежнее состояние: ./backups/pre-restore/" >&2
  exit "$restore_rc"
fi

echo "✓ восстановлено из $DUMP"
