import Foundation
import SwiftUI

/// Ключ локализации как значение.
///
/// Нужен там, где SwiftUI не принимает `LocalizedStringKey`: подписи accessibility,
/// `LabelTag(text:)`, тексты ошибок, заголовки, собранные из данных. Ключ хранится
/// строкой, из неё получаются и `String`, и `LocalizedStringKey` — так один и тот же
/// ключ работает в обоих местах, и в вью не появляется хардкода.
///
/// Отдельный тип, а не перегрузка `String(localized:)`: перегрузка со `String`
/// конфликтовала бы со стандартной `String(localized: String.LocalizationValue)`,
/// потому что `LocalizationValue` выражается строковым литералом.
struct L10n: Hashable, Sendable, ExpressibleByStringLiteral, ExpressibleByStringInterpolation {
    let key: String

    init(_ key: String) { self.key = key }
    init(stringLiteral value: String) { self.key = value }

    /// Локализованная строка.
    var text: String {
        NSLocalizedString(key, bundle: .main, comment: "")
    }

    /// Ключ для SwiftUI-вью.
    var localizedKey: LocalizedStringKey { LocalizedStringKey(key) }

    /// Локализованная строка с подстановкой аргументов.
    ///
    /// Для ключей вида `"today.selfcheckDue"` → `"Неделя %lld пройдена"`. Позиционные
    /// спецификаторы (`%1$lld`) сохраняются: в других языках порядок слов иной.
    func format(_ arguments: CVarArg...) -> String {
        String(format: text, arguments: arguments)
    }
}

extension Text {
    init(_ key: L10n) {
        self.init(key.localizedKey)
    }
}
