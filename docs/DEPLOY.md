# Деплой Mental Club на VPS (рядом с rhythmos)

Тот же сервер, что rhythmos (108.181.215.222, домен rhythmos.online), Docker + docker-compose,
host nginx + certbot. Mental изолирован: свои контейнеры (`mental-*`), сеть, том, порты
**8010** (backend) и **8011** (bot-webhook). Бот — через **webhook** на сабдомене
`mental.rhythmos.online`.

Артефакты в репозитории: `docker-compose.prod.yml`, `backend/Dockerfile`+`docker-entrypoint.sh`,
`bot/Dockerfile`, `deploy.sh`, `infra/nginx/mental.rhythmos.online.conf`, `*.env*.example`.

---

## 0. Предпосылки на сервере
Docker и docker-compose уже стоят (для rhythmos). Порты 8010/8011 свободны (rhythmos занимает 8000/8001).

## 1. DNS
Добавить A-запись **`mental.rhythmos.online` → 108.181.215.222** (у регистратора/DNS домена).
Дождаться распространения (`dig +short mental.rhythmos.online`).

## 2. Код на сервер
Вариант A (git): создать приватный репозиторий, запушить, на сервере склонировать в `/srv/mental`.
```bash
sudo mkdir -p /srv/mental && sudo chown $USER /srv/mental
git clone <repo-url> /srv/mental && cd /srv/mental
```
Вариант B (без git): `rsync -av --exclude .venv --exclude '*.db' ~/dev/mental/ user@host:/srv/mental/`

## 3. Секреты (.env)
```bash
cd /srv/mental
cp .env.example .env                         # DB_PASSWORD — задать надёжный
cp backend/.env.prod.example backend/.env.prod   # OPENAI_API_KEY, LLM_PROVIDER
cp bot/.env.prod.example bot/.env.prod           # BOT_TOKEN, WEBHOOK_*, TESTER_IDS, OPENAI_API_KEY
```
В `bot/.env.prod`: `USE_WEBHOOK=true`, `WEBHOOK_BASE=https://mental.rhythmos.online`,
`WEBHOOK_SECRET=<случайная строка>`, `API_BASE_URL=http://backend:8000` (имя сервиса в сети).

## 4. Поднять контейнеры
```bash
cd /srv/mental
./deploy.sh          # = docker-compose -f docker-compose.prod.yml up -d --build
# backend на старте сам делает: alembic upgrade head + load_content (см. docker-entrypoint.sh)
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f backend
```
Проверка API локально: `curl -s http://127.0.0.1:8010/health` → `{"status":"ok"}`.

⚠️ Первый запуск на Postgres: убедиться, что `alembic upgrade head` прошёл без ошибок
(локально проверяли на SQLite). Если миграция споткнётся на PG — глянуть логи backend.

## 5. Nginx + SSL (host)
```bash
sudo cp infra/nginx/mental.rhythmos.online.conf /etc/nginx/sites-available/mental.rhythmos.online
sudo ln -s /etc/nginx/sites-available/mental.rhythmos.online /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d mental.rhythmos.online     # выдаст SSL, допишет 443-блок и редирект
```
Проверка снаружи: `curl -s https://mental.rhythmos.online/health` → `{"status":"ok"}`.

## 6. Webhook бота
Бот сам ставит webhook при старте (`bot/main.py`, `USE_WEBHOOK=true`) на
`WEBHOOK_BASE + WEBHOOK_PATH`. Проверить:
```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
# url должен быть https://mental.rhythmos.online/tg/webhook, pending_update_count маленький
docker-compose -f docker-compose.prod.yml logs bot | grep -i webhook
```
Затем написать боту `/start` в Telegram.

## 7. Обновления
```bash
cd /srv/mental && ./deploy.sh          # git pull + up -d --build
# только бэкенд/бот:
docker-compose -f docker-compose.prod.yml up -d --build backend bot
```

## Заметки / что учесть
- **Один токен = один getUpdates/webhook.** Локальный polling-бот на этом же токене нужно
  ВЫКЛЮЧИТЬ, иначе конфликт с webhook. Для прода лучше отдельный бот от @BotFather.
- **Напоминания:** планировщик работает внутри контейнера бота (restart: unless-stopped) —
  always-on, поэтому пропаданий, как в dev-песочнице, не будет.
- **FSM на MemoryStorage:** при рестарте контейнера бота состояние «идёт день» теряется
  (есть авто-восстановление с бэкенда). Если захочется переживать рестарты без перепрохождения —
  подключить персистентный FSM-storage (Redis/SQLite) — TODO.
- **Внутренние эндпоинты** `/reminders/due` и `/reminders/mark` сейчас без авторизации.
  Они слушают только 127.0.0.1:8010 (через nginx наружу отдаётся, но путь можно закрыть).
  На всякий случай в nginx можно ограничить `/reminders/` — TODO.
- **Postgres-бэкапы:** `docker exec mental-db pg_dump -U mental mental > backup.sql` (по крону).
- **WhatsApp (позже):** identity уже мультиканальный (`provider=whatsapp`). Нужен Meta/Twilio
  аккаунт + номер + webhook-роутер на бэкенде (образец — `rhythmos/backend/app/routers/whatsapp.py`).
