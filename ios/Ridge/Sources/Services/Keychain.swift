import Foundation
import Security

/// Хранилище токена сессии в Keychain.
///
/// В Rhythmos JWT и user id лежали в `UserDefaults` — то есть в открытом plist внутри
/// контейнера приложения, попадающем в резервные копии. Здесь Keychain с
/// `kSecAttrAccessibleAfterFirstUnlock`: доступно фоновым задачам после первой
/// разблокировки, но не переезжает на другое устройство через бэкап.
enum Keychain {
    private static let service = "day.ridge.app.session"

    enum Key: String {
        case accessToken = "access_token"
        case userId = "user_id"
    }

    static func set(_ value: String?, for key: Key) {
        guard let value, !value.isEmpty else {
            remove(key)
            return
        }
        let data = Data(value.utf8)
        var query = baseQuery(key)

        // сначала пробуем обновить существующую запись, иначе добавляем новую
        let attributes: [String: Any] = [kSecValueData as String: data]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            query[kSecValueData as String] = data
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            SecItemAdd(query as CFDictionary, nil)
        }
    }

    static func get(_ key: Key) -> String? {
        var query = baseQuery(key)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let string = String(data: data, encoding: .utf8)
        else { return nil }
        return string
    }

    static func remove(_ key: Key) {
        SecItemDelete(baseQuery(key) as CFDictionary)
    }

    static func removeAll() {
        Key.allKeys.forEach(remove)
    }

    private static func baseQuery(_ key: Key) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
        ]
    }
}

extension Keychain.Key {
    static var allKeys: [Keychain.Key] { [.accessToken, .userId] }
}
