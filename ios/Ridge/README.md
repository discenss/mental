# Ridge — iOS-клиент Mental

SwiftUI-приложение под iOS 17+, работающее против бэкенда Mental (`~/dev/mental/backend`).
Скелет и визуальный язык унаследованы от Rhythmos; предметная логика — Mental.

> **Этот код ни разу не компилировался.** Он написан на Linux, где нет Xcode.
> Ожидайте ошибок сборки при первом открытии — см. «Что проверить в первую очередь».

## Быстрый старт

```bash
brew install xcodegen                 # .xcodeproj не в репозитории, он генерируется
cd ios/Ridge
cp Config/Local.xcconfig.example Config/Local.xcconfig
$EDITOR Config/Local.xcconfig         # впишите свой Team ID
xcodegen generate
open Ridge.xcodeproj
```

Локальный бэкенд для Debug-сборки (адрес уже прописан в `Config/Debug.xcconfig`):

```bash
cd ~/dev/mental/backend
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Симулятор ходит на `127.0.0.1:8000` хоста. Для устройства замените
`RIDGE_API_BASE_URL` в `Debug.xcconfig` на IP машины.

## Структура

```
Config/          xcconfig-и: Team ID и bundle id вне UI Xcode
  Shared         общие настройки; подключает Local.xcconfig
  Debug/Beta/Release   bundle id, PRODUCT_NAME, адрес API, режим APNs
  Local.xcconfig       Team ID — в .gitignore, не коммитится
Sources/
  App/           точка входа, RootView, AppDelegate
  Models/        доменные enum'ы и модели ответов API
  Services/      HTTP-клиент, Keychain, пуши, диктовка, локализация, мок
  ViewModels/    @MainActor ObservableObject по экрану
  Views/         экраны
  DesignSystem/  тема, компоненты, карточки, анимации
Resources/       Localizable.xcstrings, Info.plist, entitlements
Tests/           unit-тесты на swift-testing
```

## Что проверить в первую очередь

Код не проходил компилятор. Наиболее вероятные места ошибок:

1. **`Localizable.xcstrings`** — Xcode может захотеть пересобрать каталог. Ключи с
   подстановкой записаны в форме SwiftUI (`"today.weekDay %lld %lld"`); если строка
   покажется сырым ключом — проверьте, что форма ключа совпала.
2. **Строгая конкурентность** (`SWIFT_STRICT_CONCURRENCY = complete` в `Shared.xcconfig`).
   `RidgeAPI` — actor, ViewModel'и `@MainActor`. Если Swift 6 ругается — самое простое
   временно понизить до `targeted` и разобрать предупреждения по одному.
3. **Google Sign-In** отключён: `GoogleSignInBridge.signIn()` бросает `.notConfigured`,
   кнопка скрыта, пока нет `GIDClientID` в Info.plist. Инструкция — в комментарии
   внутри `AuthView.swift`. Вход через Apple работает без этого.
4. **`AVAudioApplication.requestRecordPermission`** — API iOS 17. На более старом SDK
   замените на `AVAudioSession.sharedInstance().requestRecordPermission`.
5. **`#Preview` с сетевыми VM** покажут пустые состояния — это норма, они ходят в
   реальный API. Для наполненных превью подставьте `MockAPI`.

## Как это связано с бэкендом

| Экран | Эндпоинты |
|---|---|
| Вход | `POST /auth/apple`, `/auth/google`, `GET /auth/me`, `POST /auth/link` |
| Онбординг | `GET /intake?lang=`, `POST /intake/submit`, `GET /modules?lang=`, `POST /enroll` |
| Сегодня | `GET /enrollments/{eid}/day-steps`, `POST /open-day`, `POST /close-day` |
| Самопроверка | `GET /selfcheck-questions`, `POST /selfcheck` |
| История | `POST /journal/list`, `POST /journal` |
| Путь | `GET /enrollments/{eid}/status`, `POST /week-insight`, `/insight`, `/final-products/list` |
| Я | `POST /users/settings/update`, `/users/abandon-active`, `/devices/register` |

Токен сессии — в Keychain, уходит заголовком `Authorization: Bearer`. Бэкенд
опознаёт пользователя из токена, а не из тела запроса.

### Почему `day-steps`, а не `today`

Последовательность прохождения дня раньше строил только Telegram-бот у себя. Второй
клиент означал бы вторую реализацию и неизбежное расхождение, поэтому сборка шагов
переехала в бэкенд (`app/services/daysteps.py`). Приложение рендерит структурные
поля шага, бот — предрендеренный `text` из того же ответа. Паритет закреплён тестами
на стороне бэкенда.

## Отличия от Rhythmos (осознанные)

Исследование Rhythmos нашло дефекты, которые сюда не перенесены:

| Rhythmos | Ridge |
|---|---|
| Нет тёмной темы (25 colorset'ов без `appearances`) | Пара light/dark у каждого цвета в `Theme.swift` |
| JWT в `UserDefaults` | Keychain (`Keychain.swift`) |
| Любая ошибка `/me` = разлогин | 401 разлогинивает, офлайн — нет (`APIError.requiresSignOut`) |
| `@Environment(\.theme)` объявлен, но не используется | Используется во всех компонентах |
| Мёртвые токены `Done`/`Partial`/`Skipped` | `statusColor()`/`zoneColor()` от семантических цветов |
| `RhytmosAPI.shared` захардкожен в каждой VM | Протокол + инъекция, есть `MockAPI` |
| `URLSession.shared` без таймаутов и отмены | Своя конфигурация, `Task` хранится и отменяется |
| Нет `#Preview`, тестов, accessibility | Превью на каждом экране, тесты, подписи на контролах |
| Локализация не сделана, форматтеры на `ru_RU` | Все строки в каталоге, форматтеры от выбранного языка |
| `Package.swift`, который ничего не собирает | Нет; проект генерируется XcodeGen |

## Терминология (нормативно, §16)

- «диагностика» в интерфейсе **запрещена** — только «самопроверка»;
- не «модуль», а «маршрут» или «программа»;
- оговорка «не ставим диагнозов и не заменяем работу с психологом» — на первом экране;
- баллы самопроверки пользователю не показываются, только зона;
- обращение на «вы», тон спокойный, без давления.

Формулировки сверены с `bot/texts.py` — приложение и бот должны звучать одинаково.

## Чего ещё нет

- **Google Sign-In** — нужен SDK и `GIDClientID` (см. выше).
- **Иконка приложения** — `Resources/Assets.xcassets` пуст, AppIcon нужно добавить.
- **Постмодульная маршрутизация** (слой C) — эндпоинты есть, экрана нет.
- **Сбор финального продукта** — показ готового есть, пошаговый сбор нет.
- **Реальное аудио** — все 48 файлов на бэкенде пока одна заглушка.
