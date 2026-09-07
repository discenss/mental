import Foundation
import UIKit
import UserNotifications

/// Пуш-уведомления: разрешение, APNs device token, регистрация на бэкенде.
///
/// Напоминания шлёт бэкенд (слоты morning/afternoon/evening в таймзоне пользователя).
/// До появления ключа APNs на сервере отправка там — no-op, но клиентская часть уже
/// на месте: токен копится, и напоминания заработают без обновления приложения.
@MainActor
final class PushService: ObservableObject {
    static let shared = PushService()

    @Published private(set) var isAuthorized = false

    private let tokenKey = "ridge_apns_device_token"
    private let api: RidgeAPIProtocol

    private init(api: RidgeAPIProtocol = RidgeAPI.shared) {
        self.api = api
    }

    /// Сборка Debug/Beta работает против sandbox-шлюза APNs, Release — против prod.
    /// Токены между ними не взаимозаменяемы, поэтому флаг едет на сервер вместе с токеном.
    private var isSandbox: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "RIDGE_APNS_SANDBOX") as? String)?.uppercased() != "NO"
    }

    var storedDeviceToken: String? {
        UserDefaults.standard.string(forKey: tokenKey)
    }

    func storeDeviceToken(_ token: String) {
        UserDefaults.standard.set(token, forKey: tokenKey)
    }

    /// Спросить разрешение и подписаться на APNs.
    @discardableResult
    func requestAuthorization() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            isAuthorized = granted
            if granted {
                UIApplication.shared.registerForRemoteNotifications()
            }
            return granted
        } catch {
            isAuthorized = false
            return false
        }
    }

    func refreshAuthorizationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        isAuthorized = settings.authorizationStatus == .authorized
            || settings.authorizationStatus == .provisional
    }

    /// Отправить токен на бэкенд. Тихо ничего не делает, если токена ещё нет или
    /// пользователь не авторизован — вызывается из нескольких мест и не должен шуметь.
    func registerIfPossible() async {
        guard RidgeAPI.shared.isAuthenticated,
              let token = storedDeviceToken, !token.isEmpty else { return }
        try? await api.registerDevice(token: token,
                                      sandbox: isSandbox,
                                      language: LanguageStore.shared.current.rawValue)
    }

    /// Снять устройство с пушей при выходе из аккаунта.
    func unregister() async {
        guard let token = storedDeviceToken, !token.isEmpty else { return }
        try? await api.unregisterDevice(token: token)
    }
}
