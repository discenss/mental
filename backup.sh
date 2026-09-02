#!/usr/bin/env bash
# Дамп БД Mental Club в ./backups/mental-YYYYmmdd-HHMMSS.sql.gz
#
# Зачем: единственное невосполнимое на этом сервере — Postgres-том (пользователи, прогресс,
# дневники). Код лежит в git, образы пересобираются, а том — нет. Нужен и перед деплоем
# (миграции применяются автоматически на старте backend и не откатываются), и при переезде.
#
# Флаги:
#   --quiet        меньше вывода (используется из deploy.sh)
#   --keep N       сколько дампов хранить (по умолчанию 20)
#   --out DIR      каталог для дампов (по умолчанию ./backups)
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=lib-compose.sh
source ./lib-compose.sh

QUIET=0; KEEP=20; OUT_DIR="./backups"
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1 ;;
    --keep)  KEEP="${2:?--keep требует число}"; shift ;;
    --out)   OUT_DIR="${2:?--out требует каталог}"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "неизвестный флаг: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { [ "$QUIET" = 1 ] || echo "$@"; }

# DB_USER/DB_NAME берём из .env — те же дефолты, что в docker-compose.prod.yml
[ -f .env ] && set -a && . ./.env && set +a
DB_USER="${DB_USER:-mental}"
DB_NAME="${DB_NAME:-mental}"

DB_CONTAINER="$(container_of db)"
docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER" || {
  echo "✖ контейнер $DB_CONTAINER не запущен — нечего дампить" >&2; exit 1; }

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$OUT_DIR/mental-$STAMP.sql.gz"
TMP="$FILE.partial"

say "→ pg_dump $DB_NAME (пользователь $DB_USER)"
# Пишем во временный файл и переименовываем только после успеха: оборванный дамп,
# лежащий под правильным именем, опаснее отсутствующего — на него понадеются при restore.
if ! docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
     | gzip > "$TMP"; then
  rm -f "$TMP"
  echo "✖ pg_dump не удался" >&2
  exit 1
fi
# gzip в конце пайпа скрывает код возврата pg_dump, поэтому дополнительно проверяем,
# что дамп целый и не пустой
if ! gzip -t "$TMP" 2>/dev/null || [ ! -s "$TMP" ]; then
  rm -f "$TMP"; echo "✖ дамп повреждён или пуст" >&2; exit 1
fi
mv "$TMP" "$FILE"
say "  ✓ $FILE ($(du -h "$FILE" | cut -f1))"

# Ротация: держим последние N
if [ "$KEEP" -gt 0 ]; then
  ls -1t "$OUT_DIR"/mental-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
    say "  удаляю старый дамп: $(basename "$old")"
    rm -f "$old"
  done
fi

echo "$FILE"
