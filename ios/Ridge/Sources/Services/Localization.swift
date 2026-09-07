import Foundation
import SwiftUI

/// Язык интерфейса.
///
/// На этом этапе активен только русский, но инфраструктура готова с первого дня:
/// в Rhythmos локализацию отложили (в `Localizable.xcstrings` было 5 строк, всё
/// остальное — русский хардкод, форматтеры прибиты к `ru_RU`), и исправлять это
/// потом оказалось дорого.
enum AppLanguage: String, CaseIterable, Identifiable, Sendable {
    case ru
    case en
    case es
    case de
    case pt

    var id: String { rawValue }

    /// Активен ли язык сейчас. Остальные показываем неактивными с пометкой «скоро» —
    /// пользователь видит, что продукт будет расти, но не упирается в пустой перевод.
    var isAvailable: Bool { self == .ru }

    /// Название на самом языке — читается до того, как язык выбран.
    var nativeName: String {
        switch self {
        case .ru: return "Русский"
        case .en: return "English"
        case .es: return "Español"
        case .de: return "Deutsch"
        case .pt: return "Português"
        }
    }

    var flag: String {
        switch self {
        case .ru: return "🇷🇺"
        case .en: return "🇬🇧"
        case .es: return "🇪🇸"
        case .de: return "🇩🇪"
        case .pt: return "🇵🇹"
        }
    }

    /// Локаль для форматтеров. Именно она, а не `Locale(identifier: "ru_RU")`:
    /// даты обязаны следовать выбранному языку.
    var locale: Locale { Locale(identifier: rawValue) }
}

/// Текущий язык приложения. Хранится локально и дублируется на сервер:
/// каталожные эндпоинты берут язык из `?lang=`, все остальные — из
/// `User.preferred_language`, поэтому нужно и то и другое.
@MainActor
final class LanguageStore: ObservableObject {
    static let shared = LanguageStore()

    @AppStorage("ridge_language") private var stored: String = AppLanguage.ru.rawValue

    @Published private(set) var current: AppLanguage = .ru

    private init() {
        current = AppLanguage(rawValue: stored) ?? .ru
    }

    func set(_ language: AppLanguage) {
        guard language.isAvailable else { return }
        stored = language.rawValue
        current = language
    }

    var locale: Locale { current.locale }
}

// MARK: - Форматирование дат

/// Форматтеры дат, привязанные к ВЫБРАННОМУ языку, а не к `ru_RU`.
enum DateFormatting {
    /// «ПН · 7 СЕН» — подпись над hero-заголовком.
    static func heroDate(_ date: Date, language: AppLanguage) -> String {
        let f = DateFormatter()
        f.locale = language.locale
        f.setLocalizedDateFormatFromTemplate("EE d MMM")
        return f.string(from: date)
    }

    /// «7 сентября» — заголовок дня в истории.
    static func dayTitle(_ date: Date, language: AppLanguage) -> String {
        let f = DateFormatter()
        f.locale = language.locale
        f.setLocalizedDateFormatFromTemplate("d MMMM")
        return f.string(from: date)
    }

    /// «сентябрь 2026» — шапка календаря.
    static func monthTitle(_ date: Date, language: AppLanguage) -> String {
        let f = DateFormatter()
        f.locale = language.locale
        f.setLocalizedDateFormatFromTemplate("LLLL yyyy")
        return f.string(from: date)
    }

    /// «14:30» — время записи.
    static func time(_ date: Date, language: AppLanguage) -> String {
        let f = DateFormatter()
        f.locale = language.locale
        f.timeStyle = .short
        f.dateStyle = .none
        return f.string(from: date)
    }

    /// Короткие подписи дней недели для календаря, начиная с понедельника.
    static func weekdaySymbols(language: AppLanguage) -> [String] {
        let f = DateFormatter()
        f.locale = language.locale
        let symbols = f.veryShortStandaloneWeekdaySymbols ?? ["S", "M", "T", "W", "T", "F", "S"]
        // Foundation отдаёт с воскресенья; в продукте неделя начинается с понедельника
        return Array(symbols[1...]) + [symbols[0]]
    }
}

/// Разбор дат бэкенда.
///
/// `created_at` приходит наивным ISO **без таймзоны** — трактуем как локальное время
/// пользователя, иначе записи «уезжают» на границе суток.
enum DateParsing {
    private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let naive: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current                       // наивная строка = локальное время
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()

    private static let naiveFraction: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return f
    }()

    static func date(from string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        return naiveFraction.date(from: string)
            ?? naive.date(from: string)
            ?? withFraction.date(from: string)
            ?? plain.date(from: string)
    }
}
