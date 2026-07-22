# Mental Club — онбординг для ревью (хендофф другой сессии/модели)

Ты открываешь этот гайд, чтобы **сделать код-ревью проекта Mental Club**. Ниже — всё, что нужно:
что это, где код, как запустить, что именно ревьюить. Работай в каталоге **`~/dev/mental`**.

> Проект НЕ под git (нет репозитория) — «дифа» нет, ревьюишь весь код целиком. ~4100 строк Python + YAML-контент.
> Первым делом можно предложить владельцу `git init` для базовой гигиены.

---

## 1. Что это

**Mental Club** — продукт психологической поддержки: **линейные 6-недельные терапевтические модули**
(не адаптивный, в отличие от родительского проekта rhythmos). Модуль = 6 недель × 7 дней, единый Flow.
Реализованы 2 модуля из 10 направлений: **BOUND** («Личные границы») и **REAL** («Найти себя»).

День проходится в **две сессии**: 🌅 утро (открыть: утренние маркеры + фокус + задание) и
🌇 вечер (закрыть: статус задания + квиз + вечерние маркеры + рефлексия → следующий день).
День 7 → недельная самопроверка (10 вопросов, скрытые веса) → зона GREEN/YELLOW/RED + critical-logic.

**Диагностика — 4 слоя:** D) входная самооценка-интейк (30 вопросов → выбор модуля);
A) недельная самопроверка → зона; B) critical-answer logic; C) постмодульная маршрутизация
(REAL = тест 21 вопрос, BOUND = накопленные flags). Термин «диагностика» в UI запрещён — «самопроверка».

**Важно:** выбор маршрута и зоны — ДЕТЕРМИНИРОВАННЫЕ (правила + заготовленные тексты), НЕ ИИ.
ИИ (OpenAI) только в трёх местах: «Спросить ИИ» (будни), «Разбор недели» и «Итог модуля» (аналитика),
+ распознавание голоса (Whisper).

## 2. Где что (структура `~/dev/mental`)

```
backend/            FastAPI + SQLAlchemy 2.0 + Alembic (SQLite локально: backend/mental.db)
  app/models.py     ~30 таблиц: контент, интейк, identity, runtime
  app/main.py       все HTTP-эндпоинты
  app/services/     intake, scoring, progression (день/сессии), postmodule, settings (напоминания),
                    identity, testmode, ai
  app/content_loader.py  загрузка YAML + валидация
  alembic/          миграции
  scripts/verify_engines.py   СКВОЗНОЙ e2e-тест движков (запусти его — см. §4)
bot/                aiogram 3.13, polling
  api.py            async httpx-клиент к backend (бот без бизнес-логики)
  handlers/         start, intake, flow (день+самопроверка), test, ask, progress (путь+дневник), settings
  scheduler.py      APScheduler: раз/мин дёргает /reminders/due и шлёт напоминания
  voice.py          Whisper
content/            intake.yaml + modules/{bound,real}.yaml — эталонный контент
docs/RUNBOOK.md     ГЛАВНЫЙ документ: запуск, env, токены, ВСЕ решения и фиксы (читай целиком)
docs/mental-architecture.md   спека-мост стандарт→код (модель данных, движки, API, §-нормативы)
```

## 3. Как запустить (venv переиспользуется от rhythmos)

```bash
# зависимости — в venv /home/discens/dev/rhytmos/.venv (fastapi, sqlalchemy, aiogram, apscheduler, openai…)
cd ~/dev/mental/backend
~/dev/rhytmos/.venv/bin/alembic upgrade head
~/dev/rhytmos/.venv/bin/python -m scripts.load_content          # грузит intake + оба модуля
~/dev/rhytmos/.venv/bin/uvicorn app.main:app --port 8000        # backend
# бот (нужен bot/.env с BOT_TOKEN; для ревью не обязателен):
cd ~/dev/mental/bot && ~/dev/rhytmos/.venv/bin/python main.py
```
Проверка: `curl localhost:8000/health`, `curl localhost:8000/api/v1/modules`.
Env: `backend/.env` (DATABASE_URL, OPENAI_API_KEY, LLM_PROVIDER), `bot/.env` (BOT_TOKEN, API_BASE_URL,
OPENAI_API_KEY, TESTER_IDS). Оба в `.gitignore`.

## 4. Как проверить, что всё работает

```bash
cd ~/dev/mental/backend && ~/dev/rhytmos/.venv/bin/python -m scripts.verify_engines   # должен быть ЗЕЛЁНЫМ
```
Покрывает: интейк→маршрут, полный проход BOUND, зоны, critical-refs (оба модуля), постмодуль,
тест-режим (guard/day/program). Это твой ориентир «эталонного поведения».

## 5. На что смотреть при ревью (фокус)

**Корректность (главное):**
- `services/progression.py` — движок дня и **две сессии**: `open_day`/`close_day`/`complete_day`,
  `get_today` (session morning/evening), гейт «1 день/сутки» (`_closed_today`, `done_today`),
  продвижение недель, статусы active|selfcheck_due|completed. Ищи двойное продвижение, гонки,
  краевые случаи дня 7 / недели 6.
- `services/scoring.py` — зоны (пороги, покрытие), flags, **critical-logic** через refs `{q,opt}`+min_hits
  (плюс legacy text-fallback). Проверь границы зон и срабатывание critical.
- `services/settings.py` — напоминания: `due_reminders` (session-aware, дедуп по слотам через
  last_*_date, таймзоны pytz). Ищи двойные отправки, часовые пояса, гонку при рестарте.
- `services/intake.py` — суммирование по направлениям, tie_priority, soft-порог, сборка текста.
- `services/testmode.py` — пресеты best/worst/random, перемотка.
- **Бот↔состояния (aiogram FSM):** `handlers/flow.py` — edit-in-place карточки, `day_active`/resume,
  SkipHandler-«escape» из состояний по кнопкам меню (`keyboards.MENU_TEXTS`). Ищи потерю состояния,
  залипание FSM, гонки коллбэков.

**Безопасность / приватность:**
- LLM-guardrails в `services/ai.py` (без диагнозов/лечения; §16 стандарта) — достаточно ли строги?
- Ключи/токены: только в `.env` (в `.gitignore`)? Нет ли утечек в логи/ответы?
- **`POST /api/v1/reminders/due`** — внутренний эндпоинт без аутентификации (его дёргает бот).
  В проде должен быть закрыт — отметь это.
- Пользовательские данные: `/users/reset` (полное удаление), дневник — что в него попадает (§8:
  только рефлексии/заметки; маркеры/самопроверка — нет).

**Расхождения со спекой / долги (см. RUNBOOK §«что дальше» и §10 architecture):**
- Постмодульный тест REAL (21 вопрос) в normal-флоу бота не реализован (только авто в тест-режиме).
- Финальный продукт и REAL W6D6 `saves_free_text` в дневник пока не эмитятся.
- Наименование REAL: направление vs модуль называются по-разному.
- Аудио: поле `theme` пустое; квизы W4 BOUND — концептуальные формулировки.

## 6. Контекст решений

Полная история решений и фиксов — в **`docs/RUNBOOK.md`** (§6–§8d: интейк-роутинг, дневник по датам,
настройки/напоминания 3 слота, сброс, ручной тест-прогон, утро/вечер-сессии, фикс кнопок меню,
возврат в прерванный день, ИИ-разбор недели). Прочитай его до ревью — там объяснено «почему так».

## 7. Формат вывода ревью

Дай находки по убыванию серьёзности: файл:строка → в чём дефект → конкретный сценарий отказа →
рекомендация. Раздели на: корректность-баги / безопасность / упрощения-чистота / тест-покрытие.
Не переписывай код без запроса — сначала список находок.
