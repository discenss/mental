# Mental Club — архитектура реализации

> **Назначение:** мост между нормативом «ТОЧНЫЙ СТАНДАРТ АРХИТЕКТУРЫ МОДУЛЕЙ v1.0»
> и кодом нового проекта `~/dev/mental/`. Здесь стандарт (методология) превращается
> в модель данных, YAML-формат контента, движки и API.
> Источники: стандарт v1.0, финализированные модули REAL и BOUND.
> **При конфликте между текстом модуля и стандартом решает стандарт** (§21 норматива).

---

## 0. Ключевой сдвиг относительно rhythmos

Mental Club — **не адаптивный** продукт. Маршрут линейный и одинаковый для всех:
модуль = 6 недель × 7 дней, каждый день по единому Flow. Ветвится только
**показываемый текст** (интерпретации, доп-блоки, смежные фокусы), а не последовательность дней.

Поэтому весь «мозг» rhythmos — `routing_decision_service`, `routing`, `cycle_service`,
`journey_service`, `theme_engine` — **не переносится**. Его заменяют два простых движка:

1. **Day-progression engine** — детерминированное продвижение по дням/неделям.
2. **Scoring/zone engine** — подсчёт скрытых баллов самопроверки → зона + critical logic + флаги.

Переиспользуем из rhythmos: auth/identity (multi-provider tg/ios), JWT, link-codes,
каркас bot (aiogram, i18n, FSM, scheduler), каркас iOS (SwiftUI, APIClient, DesignSystem),
push/APNs, docker/deploy/infra, Alembic-подход, `user_notes` → основа «Мой дневник».

---

## 1. Канонический Flow (норматив §6, §22)

```
ДЕНЬ  = утро:  5 утренних маркеров → Фокус дня
        день:  Задание → статус(Сделано/Частично/Не сделано) → Аудио → Квиз
        вечер: 5 вечерних маркеров → 3 вопроса рефлексии

ДЕНЬ 7 = итоговый фокус → итоговое задание → AUDIO FINAL → квиз/фиксация
         → 3 рефлексии → недельная самопроверка(10) → зона GREEN/YELLOW/RED
         → доп-текст по критичным ответам (если сработал) → рекомендация

НЕДЕЛЯ = вводный экран → смысл → цель → результат → 7 дней → самопроверка → зоны

МОДУЛЬ = паспорт → лестница 6 недель → 5+5 маркеров → 6 недель
         → недельные самопроверки → интеграционная неделя 6 → финальный продукт
         → постмодульная маршрутизация (по архитектуре модуля)
```

**Запрет альтернативных Flow (§6.1):** усталость/сопротивление/сложный ответ НЕ порождают
параллельный маршрут. Поддержка подаётся внутри существующих блоков (фокус, доп-текст, рекомендация).

---

## 2. Четыре слоя «диагностики» (в UI слово «диагностика» запрещено, §16)

| Слой | Уровень | Когда | Механика | Влияние |
|------|---------|-------|----------|---------|
| **D. Входная самооценка** | **продукт** | один раз на входе | 30 вопросов, 10 направлений, шкала 0–4 → баллы 0–12/направление → ранжирование | **выбор стартового модуля** + 2 доп. фокуса. Право выбора за пользователем |
| **A. Недельная самопроверка** | модуль | день 7 каждой недели | 10 вопросов, скрытые веса → сумма → зона | текст интерпретации + рекомендация. **Не блокирует** переход |
| **B. Critical-answer logic** | модуль | вместе с A | конкретные критичные варианты | добавляет мягкий тематический блок. Не меняет балл, не диагноз |
| **C. Постмодульная маршрутизация** | модуль | после недели 6 | REAL: отдельный тест 21 вопрос. BOUND: накопленные flags | рекомендация след. модуля. **Автоперехода нет** |

**Слой D — продуктовый интейк-роутер** (файлы «Оценка состояния…» + «Интерпретации…»): это НЕ модульная диагностика.
Оценивает состояние по 10 направлениям и подбирает точку входа в каталог модулей. Содержимое → `content/intake.yaml`. Детали в §12.

**Входного опросника на уровне отдельного модуля нет** — «Для кого этот модуль» это текст самоузнавания. Вход в модуль даёт слой D.

Модель обязана поддерживать **оба** механизма слоя C (см. §7.4).

### 2.1. Таксономия направлений — ось всего продукта

Единый справочник из **10 кодов** (направление = тег = код модуля) пронизывает все слои:

```
D. интейк   → баллы по 10 направлениям → выбирает МОДУЛЬ
A. самопроверка → flag-вопросы Q8–10 эмитят те же теги
C. постмодуль → рекомендует следующий МОДУЛЬ по тем же тегам
```

| Код | Клиентское имя | Модуль | Статус |
|-----|----------------|--------|--------|
| BURN | Выгорание | — | будущий |
| ANX | Тревога | — | будущий |
| EMO | Эмоциональная регуляция | — | будущий |
| BOUND | Личные границы | `bound` | **реализован** |
| SELF | Самооценка | — | будущий |
| REL | Отношения | — | будущий |
| FOCUS | Прокрастинация и фокус | — | будущий |
| REAL | Реализация и смысл | `real` | план (есть контент-исходник) |
| PAST | Прошлый опыт | — | будущий |
| PROC | Процессы и паттерны | — | будущий |

Порядок в таблице = **приоритет бережности** при равных баллах (BURN→…→PROC). Каталог модулей растёт по этой оси: каждое направление ← ровно один 6-недельный модуль.

> Нейминг к согласованию: направление `REAL` = «Реализация и смысл», а модуль-исходник REAL называется «Найти себя». Смысл совпадает, клиентское имя расходится.

---

## 3. Модель данных

Именование полей адаптируемо к backend, но **смысловые сущности разделены** (норматив §19:
не хранить всё как один `content_block` без типа). Ниже — целевые таблицы.

### 3.1. Контент (статика, версионируется; загрузка из YAML → БД)

```
modules
  id, code (REAL|BOUND|...), name, subtitle,
  passport            JSON   -- см. §4 (для кого, что будет, зачем, результаты, границы)
  content_version     str    -- semver; см. §8
  final_product_kind  str    -- protocol|map|orientation|plan|algorithm
  postmodule_kind     str    -- test|flags|none  (механика слоя C)

module_weeks
  id, module_id, n (1..6),
  title, intro_screen TEXT,  -- 4–7 абзацев
  meaning TEXT,              -- методологический смысл недели
  goal TEXT,                 -- 1 абзац
  result TEXT,               -- ожидаемый промежуточный результат
  key_themes JSON

module_days
  id, module_id, week_n, day_n (1..7), title

day_focus         module_id, week_n, day_n, text          -- 2–5 абзацев
day_task          module_id, week_n, day_n, text, subtasks JSON?  -- практика; статус отдельно
day_quiz          module_id, week_n, day_n,
                    kind (progress|concept),
                    question, options JSON,                -- [{text, correct?}]
                    saves_free_text BOOL                   -- REAL W6D6 = true (формула ориентира)
day_reflection    module_id, week_n, day_n, q1, q2, q3     -- свободный текст, необязательно

markers                                                    -- 5 утр + 5 веч, КОНСТАНТЫ модуля
  id, module_id, phase (morning|evening), idx (1..5),
    question, options JSON                                 -- [{label}]; без весов, не в дневник

week6_intent_questions  module_id, day_n, q1, q2, q3       -- BOUND-спец: доп. утр. вопросы намерения

audio_assets
  id, module_id, week_n, slot (A1|A2|A3|FINAL),
    code,   -- AUDIO_{MODULE}_W{n}_{slot}
    day_range,  -- A1:1-2 A2:3-4 A3:5-6 FINAL:7
    title, theme

selfcheck_questions
  id, module_id, week_n, q_index (1..10),
    kind (core|flag),        -- Q1 регулярность, Q2-7 core, Q8-10 flag
    tag,                     -- для flag-вопросов: ANX|SELF|REL|EMO|BURN|PROC|FOCUS|PAST
    question,
    options JSON             -- [{text, weight 0..3, flag_weight 0..2?, critical BOOL}]

zone_interps
  id, module_id, week_n (0 = финал модуля),
    zone (GREEN|YELLOW|RED),
    score_min, score_max,    -- диапазоны модуль-специфичны, взаимоисключающи, покрывают весь range
    sys_action, meaning,     -- для методолога
    user_text, recommendation

critical_triggers
  id, module_id, week_n,
    condition,               -- напр. "Q8 in {opt_a} OR Q1 == not_done"
    critical_options JSON,
    additional_text          -- 80–180 слов, тематический

final_product_template
  module_id, sections JSON   -- BOUND: 9 разделов протокола; REAL: формула ориентира

postmodule_test              -- только если postmodule_kind == test (REAL)
  module_id, topics JSON     -- [{tag, questions:[{q, options:[{text, weight}]}]}]
```

### 3.2. Состояние пользователя (runtime)

```
enrollments
  id, user_id, module_id, started_at,
    current_week, current_day, status (active|week_done|completed|paused)

daily_entries                -- один ряд на пользователя на день модуля
  id, enrollment_id, week_n, day_n, date,
    morning_answers JSON,    -- ответы 5 утр. маркеров (+ intent-вопросы для W6)
    task_status (DONE|PARTIAL|NOT_DONE),
    task_answer JSON?,       -- ответы задания (в дневник по желанию)
    quiz_answer,
    evening_answers JSON,    -- ответы 5 веч. маркеров
    reflection_answers JSON  -- 3 ответа (в дневник по желанию)

selfcheck_results
  id, enrollment_id, week_n,
    core_score, zone,
    triggered_criticals JSON,
    flags JSON               -- {tag: weight}  накапливаемые для слоя C (BOUND)

flag_accumulator             -- денормализованный cross-week агрегат (BOUND-стиль)
  enrollment_id, tag, total_weight, weeks_hit

journal_entries              -- «Мой дневник»
  id, user_id, source_type (task|reflection|final_product|note),
    ref_id, module_id, week_n?, day_n?, text, created_at

final_product_instances
  id, enrollment_id, saved_content JSON

postmodule_results
  id, enrollment_id, topic_scores JSON, recommended_modules JSON
```

### 3.3. Рекомендованные ID (норматив §19) — соответствие

| Сущность | ID-схема |
|----------|----------|
| Модуль | `REAL`, `BOUND`, `ANX`… |
| Неделя / День | `{MOD}_W{n}` / `{MOD}_W{n}_D{d}` |
| Маркер | `{MOD}_AM_M1..M5` / `{MOD}_PM_M1..M5` |
| Фокус/Задание | `{MOD}_W{n}_D{d}_FOCUS` / `_TASK` |
| Статус задания | `TASK_STATUS: DONE\|PARTIAL\|NOT_DONE` |
| Аудио | `AUDIO_{MOD}_W{n}_{A1\|A2\|A3\|FINAL}` |
| Квиз/Рефлексия | `..._QUIZ` / `..._REFLECTION_Q1..Q3` |
| Самопроверка | `{MOD}_W{n}_SELFCHECK_Q1..Q10` |
| Зона / Критичный | `GREEN\|YELLOW\|RED` / `CRITICAL_TRIGGER_ID` |
| Финал / Смежный тег | `{MOD}_FINAL_PROTOCOL` / `ADJACENT_TOPIC_TAG` |

---

## 4. Паспорт модуля (JSON, норматив §3, §18.1)

```yaml
passport:
  name: "Личные границы"
  intro: "2–4 абзаца описания состояния/проблемы"
  for_whom: [ "10–20 конкретных пунктов самоузнавания" ]
  extra_support: "2–4 абзаца: когда самостоятельный маршрут только вспомогательный"
  what_happens: { intro: "...", transitions: ["5–7 переходов"] }
  why: "2–4 абзаца"
  what_user_gets: [ "8–15 пунктов" ]
  main_result: "1 абзац — реалистичный психологический переход, не гарантия"
  important: "2–4 абзаца — границы метода, безопасный темп"
```

---

## 5. YAML-формат контента модуля

Один файл на модуль: `content/modules/{code}.yaml`. Скелет:

```yaml
module:
  code: BOUND
  name: "Личные границы"
  subtitle: null
  content_version: "1.0.0"
  final_product_kind: protocol
  postmodule_kind: flags          # REAL → test

passport: { ... }                 # §4

markers:
  morning:                        # 5, константы
    - { idx: 1, question: "...", options: [Да, Скорее да, Скорее нет, Нет] }
    # ...M5
  evening: [ ... ]                # 5

audio_map:                        # 24 = 6 недель × 4
  - { week: 1, slot: A1, code: AUDIO_BOUND_W1_A1, days: "1-2", title: "...", theme: "..." }
  # ...

weeks:
  - n: 1
    title: "..."
    intro_screen: "..."
    meaning: "..."
    goal: "..."
    result: "..."
    key_themes: [ ... ]
    days:
      - d: 1
        title: "..."
        focus: "..."
        task: { text: "...", subtasks: [] }
        quiz: { kind: progress, question: "...", options: [...], saves_free_text: false }
        reflection: [ "q1", "q2", "q3" ]
      # ...d7 (итоговые фокус/задание, AUDIO FINAL)
    selfcheck:                    # 10 вопросов
      - { q: 1, kind: core, question: "...",
          options: [ {text: "...", weight: 3}, {text: "...", weight: 2, critical: true}, ... ] }
      # Q8-10: kind: flag, tag: ANX, options c flag_weight 0..2
    zones:                        # диапазоны модуль-специфичны, проверяются математически
      - { zone: GREEN,  min: 17, max: 21, user_text: "...", recommendation: "...",
          sys_action: "open_next_week", meaning: "..." }
      - { zone: YELLOW, min: 10, max: 16, ... }
      - { zone: RED,    min: 0,  max: 9,  ... }
    critical_triggers:
      - { condition: "...", options: [...], additional_text: "80–180 слов" }

final_product:
  sections: [ "ранние сигналы", "где теряю себя", ... ]   # BOUND: 9 разделов

postmodule:                       # только при postmodule_kind: test (REAL)
  topics:
    - { tag: ANX, questions: [ {q: "...", options: [{text, weight}]} ] }
```

---

## 6. Загрузка и валидация контента

Лоадер при старте читает `content/modules/*.yaml` → БД (как rhythmos кэширует YAML).
Обязательные проверки перед публикацией (норматив §20):

- ровно 6 недель × 7 дней; 5+5 маркеров; 3 вопроса рефлексии/день; 10 вопросов самопроверки/неделя;
- **24 аудио** (6×4), коды уникальны, нет «7 аудио дня»;
- у **всех** вариантов самопроверки есть однозначные веса; посчитаны min/max score;
- зоны GREEN/YELLOW/RED **не пересекаются, без разрывов, покрывают весь диапазон** (математическая проверка);
- каждая зона имеет sys_action + meaning + user_text + recommendation;
- критичные варианты перечислены конкретно; доп-текст тематический;
- нет служебных placeholder-ов «дописать/финализировать».

---

## 7. Движки

### 7.1. Day-progression engine
Детерминированный и **time-agnostic**: `current_week/current_day` продвигается по вызову
`complete_day` — проверки даты в бэкенде нет. Дневной гейт «1 день/сутки» — забота клиента
(бота/планировщика), не бэкенда. После дня 7 → самопроверка → **следующая неделя открывается
всегда** (§9.4, §10). Блокировок нет. Статусы: `active | selfcheck_due | completed`.

**Тест-режим** (`enrollment.mode='test'`): сервис `testmode.run(scope=day|week|program,
preset=best|worst|random)` перематывает без гейта и отдаёт транскрипт выдачи движка на каждом шаге
(фокус/задание/квиз/маркеры/зона/интерпретация/critical/постмодуль) — для тестировщиков.
Эндпоинт `/enrollments/{id}/test/advance` доступен только при `mode='test'` (иначе 403);
кто получает test-режим — решает клиент (allowlist в боте).

### 7.2. Scoring/zone engine
```
core_score  = Σ weight(ответ) по Q1..Q7   (или Q1..Q10 в финале модуля)
zone        = зона, в чей [min,max] попал core_score
flags[tag] += flag_weight(ответ) по Q8..Q10
```
Пользователь **не видит** баллы (§16). Возвращает: zone, user_text, recommendation.

### 7.3. Critical-answer logic
Триггер задаётся ссылками `refs: [{q, opt}]` на конкретные варианты самопроверки + `min_hits`
(сколько refs должно совпасть). Срабатывает, если число выбранных ref-вариантов ≥ `min_hits`
→ к интерпретации добавляется `additional_text`. Legacy-поле `options` (тексты вариантов) —
fallback, если `refs` пусты. **Не меняет балл, не блокирует, не диагноз, без слов «критично/красный флаг»** (§11.3).

Оба модуля нормализованы на refs (один триггер на неделю):
- **BOUND** W1–5 → refs = flag-варианты Q8/Q9/Q10 с `flag_weight==2` (min_hits=1);
  W6 (финал) → refs = худшие (0) варианты core-вопросов, min_hits=4 («несколько устойчивых признаков»).
- **REAL** W1–6 → refs = худшие (0) варианты ключевых вопросов самопроверки (min_hits=1);
  сопоставлены по совпадению токенов «вопрос+вариант».
Legacy text-match (`options`) сохранён в движке как fallback, но в контенте не используется.

### 7.4. Постмодульная маршрутизация (два режима)
- **`kind: test`** (REAL): 21 вопрос (7 тем × 3), балл по каждой теме max 9;
  пороги 0–2 слабо / 3–5 умеренно / 6–9 заметно → рекомендовать модуль.
  Приоритет при равенстве: ANX, SELF, FOCUS, REL, BURN, EMO, PAST.
- **`kind: flags`** (BOUND): используются накопленные `flag_accumulator` из недель 1–5;
  смежный фокус, если тег набрал вес 2 в ≥2 неделях **или** сумма ≥4; максимум 2 фокуса;
  при равенстве приоритет тегу, повторившемуся в большем числе недель.
- В обоих: **автоперехода нет**, пользователь выбирает сам; текст «вам нужен другой модуль» запрещён.

---

## 8. «Мой дневник» (норматив §12)

**Сохраняется:** ответы заданий, ежедневная рефлексия, выводы дня 7, финальный продукт, личные заметки.
**НЕ сохраняется:** утренние/вечерние маркеры, техотметка выполнения, квизы, самопроверка и её баллы.
Сохранение **добровольно** — кнопка-предложение, не условие завершения дня.
Исключение: REAL W6D6 квиз = авто-сохраняемая формула ориентира (`day_quiz.saves_free_text = true`).

---

## 9. API (эскиз; JWT для iOS, telegram_id для бота — как в rhythmos)

```
GET  /api/v1/modules                          — каталог модулей (паспорта)
POST /api/v1/enroll                            — начать модуль
GET  /api/v1/today                             — текущий день: фокус, задание, аудио, квиз, маркеры
POST /api/v1/day/morning                       — ответы утр. маркеров
POST /api/v1/day/task-status                   — DONE|PARTIAL|NOT_DONE (+ task_answer в дневник)
POST /api/v1/day/quiz                           — ответ квиза
POST /api/v1/day/evening                       — веч. маркеры + 3 рефлексии
POST /api/v1/week/selfcheck                    — 10 ответов → {zone, user_text, recommendation, criticals}
GET  /api/v1/journal                            — «Мой дневник»
POST /api/v1/module/final-product              — сохранить финальный продукт
POST /api/v1/postmodule                        — постмодульный тест/маршрутизация → recommended_modules
```

---

## 10. Расхождения «файл vs стандарт» — унифицировать при заносе контента

1. **Аудио.** REAL описывает 42 (по дню). Стандарт и BOUND — **24 (4/неделю)**. → REAL приводим к 24.
2. **Максимумы/зоны.** REAL нед. max 30 (23-30/14-22/0-13); BOUND нед.1–5 max 21 (17-21/10-16/0-9),
   финал max 30. → модуль-специфично by design, держим в YAML `zones`, не в коде.
3. **BOUND неделя 4 дрейфует:** ✅ унифицировано при заносе — техотметка → 3 варианта (runtime), квизы `concept→progress` (верный ответ сохранён как `internal_correct`), `mini_explanation` влит в `focus`. Остаётся: сами формулировки вопросов квизов W4 всё ещё концептуальные — переписать при желании.
4. ✅ W6 зоны (была дыра 28–30) → GREEN 22–30. ✅ OCR «пользовательы»→«клиенты» (W5D1). Аудио-названия проставлены из сводной аудиокарты; поле `theme` пустое (в исходнике тем нет).

---

## 11. Терминология UI (норматив §16)

Использовать: **модуль/маршрут, пользователь, самопроверка, Итоги недели, фокус дня, задание дня,
Мой дневник, Сделано/Частично/Не сделано, рекомендация**.
НЕ использовать в UI: клиент, пациент, диагностика, core score, технический тег, баллы,
RED trigger/critical flag, «не прошёл/провалил неделю».
Тон: спокойный, взрослый, без мотивационной агрессии и драматизации.

---

## 12. Входная самооценка (слой D) — продуктовый интейк-роутер

Точка входа в продукт. Содержимое → `content/intake.yaml` (собрано, провалидировано). Проходится один раз;
результат — рекомендованный стартовый модуль + 2 доп. фокуса. Право выбора остаётся за пользователем.

### 12.1. Механика
- **30 вопросов**, по 3 на каждое из 10 направлений (см. §2.1). Шкала ответов единая: **0–4**
  (совсем не про меня / редко / иногда / часто / почти всегда). Ориентир — последние 2–4 недели.
- **Балл направления** = сумма его 3 вопросов → 0–12. Веса вопросов равные (скрытых весов нет).
- **Пороги (внутренние):** 0–3 слабо / 4–6 фон / 7–9 значимо / 10–12 ведущая.
- **Выбор маршрута:** сорт по убыванию → 1-е = ведущий, 2-е = фокус-1, 3-е = фокус-2.
  При равенстве — приоритет бережности `BURN,ANX,EMO,BOUND,SELF,REL,FOCUS,REAL,PAST,PROC`.
  Если ведущий < **7** → мягкая формулировка «ярко выраженной темы не выявлено…».
- Баллы/сортировка/пороги пользователю **не видны**. Доп. фокусы **не запускают** доп. тестов.

### 12.2. Тексты (в `intake.yaml → interpretations`)
Итог собирается из блоков: `static.pre_result` (1 раз) → `leading[код]` (ведущий) →
`focus1[код]` + `focus2[код]` (доп. фокусы, тон мягче) → `static.outro`. Всего **10×3 = 30**
клиентских блоков + 3 статических. Каркас сборки — `static.result_template`.

### 12.3. Модель данных
```
users               id, preferred_language, timezone, created_at
user_identities     id, user_id→users, provider(telegram|ios|whatsapp), provider_user_id  UNIQUE(provider,provider_user_id)
                    # резолвер identity.resolve_or_create(provider, provider_user_id) → единый User;
                    # все runtime user_id — FK на users.id. Каналы приносят свой provider_user_id (telegram_id/…)
intake_directions   code, name_short, name_leading, purpose, questions[], tie_priority(1-10), module_id?(null для будущих)
intake_questions    n(1-30), direction_code, text          # веса не нужны, ответы равновесны
intake_interps      direction_code, slot(leading|focus1|focus2), client_text   + 3 static (pre_result/result_template/outro)
intake_results      user_id, completed_at, scores{code:0-12}, leading, focus1, focus2, is_soft(bool), chosen_module_id
```
`intake_results.chosen_module_id` ≠ `leading` допустимо — пользователь вправе выбрать другой модуль.

### 12.4. Связь со слоем C
Слой D (вход, выбор модуля) и слой C (постмодуль, следующий модуль) используют **одну ось тегов**,
но это разные события и разные наборы вопросов. В предоставленных файлах интейка постмодульный тест
не описан — сравнивать механики дословно нельзя; общая только таксономия направлений.
