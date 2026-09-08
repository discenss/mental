import Foundation

/// Доменные перечисления Ridge.
///
/// Декодирование намеренно мягкое: бэкенд объявляет тела запросов как `payload: dict`
/// без Pydantic-моделей, схем запросов в `/openapi.json` нет, и незнакомое значение
/// не должно ронять экран. Поэтому у каждого enum есть `unknown`-ветка или
/// `init?(rawValue:)` с фолбэком.

// MARK: - Статус задания дня

enum TaskStatus: String, Codable, CaseIterable, Sendable {
    case done = "DONE"
    case partial = "PARTIAL"
    case notDone = "NOT_DONE"

    /// Пользовательская подпись. Термины из бота (`bot/texts.py`) — каналы говорят одним языком.
    var titleKey: String {
        switch self {
        case .done:    return "task.status.done"
        case .partial: return "task.status.partial"
        case .notDone: return "task.status.notDone"
        }
    }

    var symbol: String {
        switch self {
        case .done:    return "checkmark.circle.fill"
        case .partial: return "circle.lefthalf.filled"
        case .notDone: return "circle"
        }
    }
}

// MARK: - Зона недели

enum Zone: String, Codable, Sendable {
    case green = "GREEN"
    case yellow = "YELLOW"
    case red = "RED"

    /// Баллы пользователю не показываются (§16) — только зона и её текст.
    var titleKey: String {
        switch self {
        case .green:  return "zone.green"
        case .yellow: return "zone.yellow"
        case .red:    return "zone.red"
        }
    }

    var symbol: String {
        switch self {
        case .green:  return "circle.fill"
        case .yellow: return "circle.fill"
        case .red:    return "circle.fill"
        }
    }
}

// MARK: - Состояние программы

enum EnrollmentStatus: String, Codable, Sendable {
    case active
    case selfcheckDue = "selfcheck_due"
    case completed
    case abandoned

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = EnrollmentStatus(rawValue: raw) ?? .active
    }
}

// MARK: - Сессия дня

/// Утро/вечер — это два разных НАБОРА вопросов (вход в день / итог дня), а не время суток.
/// Деление контентное; см. RIDGE-IOS-PROMPT §4 и коммит 9990668.
enum DaySession: String, Codable, Sendable {
    case morning
    case evening
}

// MARK: - Тип шага дня

/// Виды шагов, которые отдаёт `GET /enrollments/{eid}/day-steps`.
/// Собираются на бэкенде (`app/services/daysteps.py`), чтобы iOS и Telegram проходили
/// день одинаково и логика не разъехалась между двумя реализациями.
enum DayStepKind: String, Codable, Sendable {
    case info
    case focustask
    case audio
    case quiz
    case freeText = "free_text"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = DayStepKind(rawValue: raw) ?? .unknown
    }

    var symbol: String {
        switch self {
        case .info:      return "text.alignleft"
        case .focustask: return "target"
        case .audio:     return "headphones"
        case .quiz:      return "checklist"
        case .freeText:  return "square.and.pencil"
        case .unknown:   return "questionmark.circle"
        }
    }
}

// MARK: - Тип записи в дневнике

enum JournalSourceType: String, Codable, Sendable {
    case task
    case reflection
    case finalProduct = "final_product"
    case note
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = JournalSourceType(rawValue: raw) ?? .unknown
    }

    var titleKey: String {
        switch self {
        case .task:         return "journal.type.task"
        case .reflection:   return "journal.type.reflection"
        case .finalProduct: return "journal.type.finalProduct"
        case .note:         return "journal.type.note"
        case .unknown:      return "journal.type.note"
        }
    }

    var symbol: String {
        switch self {
        case .task:         return "checkmark.square"
        case .reflection:   return "quote.opening"
        case .finalProduct: return "doc.text"
        case .note:         return "pencil"
        case .unknown:      return "doc"
        }
    }
}

// MARK: - Направления интейка (§2.1 архитектуры)

/// 10 направлений входной самооценки. Порядок в `allCases` = приоритет бережности
/// при равных баллах (BURN→…→PROC), как в бэкенде.
enum Direction: String, Codable, CaseIterable, Sendable {
    case burn = "BURN"
    case anx = "ANX"
    case emo = "EMO"
    case bound = "BOUND"
    case selfEsteem = "SELF"
    case rel = "REL"
    case focus = "FOCUS"
    case real = "REAL"
    case past = "PAST"
    case proc = "PROC"

    /// SF Symbol направления. Растровых ассетов нет намеренно: символы бесплатны по весу,
    /// сами подстраиваются под кегль, тему и Dynamic Type (§3.3 брифа).
    var symbol: String {
        switch self {
        case .burn:       return "battery.25"
        case .anx:        return "wind"
        case .emo:        return "cloud.rain"
        case .bound:      return "lock.shield"
        case .selfEsteem: return "person.fill.questionmark"
        case .rel:        return "person.2"
        case .focus:      return "scope"
        case .real:       return "compass.drawing"
        case .past:       return "clock.arrow.circlepath"
        case .proc:       return "arrow.triangle.2.circlepath"
        }
    }

    /// Клиентское имя направления. Реальные названия приходят с бэкенда вместе с
    /// вопросами; это фолбэк для оффлайна и превью.
    var titleKey: String { "direction.\(rawValue.lowercased())" }
}

// MARK: - Слот аудио

/// Соответствие дня и слота: 1–2 → A1, 3–4 → A2, 5–6 → A3, 7 → FINAL.
/// 24 аудио на программу (6 недель × 4), НЕ по одному на день.
enum AudioSlot: String, Sendable {
    case a1 = "A1"
    case a2 = "A2"
    case a3 = "A3"
    case final = "FINAL"

    init(day: Int) {
        switch day {
        case 1, 2: self = .a1
        case 3, 4: self = .a2
        case 5, 6: self = .a3
        default:   self = .final
        }
    }
}
