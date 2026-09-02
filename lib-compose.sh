#!/usr/bin/env bash
# Общая часть для deploy.sh / backup.sh / restore.sh: найти рабочий docker compose.
#
# Почему это отдельный файл, а не строчка в каждом скрипте: на серверах живут ДВЕ разные
# реализации compose, и выбор между ними — не косметика.
#   v2 «docker compose» (плагин)  — поддерживается, умеет читать метаданные современных образов;
#   v1 «docker-compose» (Python)  — заброшен с 2021, на Docker 26+ падает при ПЕРЕСОЗДАНИИ
#                                   контейнера с ошибкой KeyError: 'ContainerConfig',
#                                   потому что не знает нового формата image config.
# Именно на этом деплой однажды упал на полпути: образ собрался, старый контейнер уже снят,
# новый создать не смогли — прод остался с лежащим backend.
#
# Поэтому: предпочитаем v2 всегда; на v1 работаем, но громко предупреждаем, а рискованные
# операции пересоздания в deploy.sh делаем через явные rm+up, а не через «up» поверх.

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

COMPOSE_KIND=""       # v2 | v1
COMPOSE_BIN=()        # массив: как звать compose

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_KIND="v2"
    COMPOSE_BIN=(docker compose -f "$COMPOSE_FILE")
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_KIND="v1"
    COMPOSE_BIN=(docker-compose -f "$COMPOSE_FILE")
    cat >&2 <<'WARN'
⚠️  Найден только docker-compose v1 (заброшен с 2021).
    На свежих версиях Docker он падает при пересоздании контейнеров
    (KeyError: 'ContainerConfig') и может оставить сервис лежащим.
    Поставь плагин v2 — sudo не нужен, ставится в домашний каталог:

      mkdir -p ~/.docker/cli-plugins
      V=$(curl -s https://api.github.com/repos/docker/compose/releases/latest \
            | grep -oP '"tag_name": "\K[^"]+')
      curl -sSL -o ~/.docker/cli-plugins/docker-compose \
        "https://github.com/docker/compose/releases/download/${V}/docker-compose-linux-$(uname -m)"
      chmod +x ~/.docker/cli-plugins/docker-compose

WARN
    return 0
  fi
  echo "✖ Не найден ни 'docker compose' (v2), ни 'docker-compose' (v1). Установи Docker Compose." >&2
  exit 1
}

compose() { "${COMPOSE_BIN[@]}" "$@"; }

# Имя сервиса → имя контейнера (container_name задан в compose-файле)
container_of() { echo "mental-$1"; }
