import SwiftUI
import UIKit
import UserNotifications

@main
struct RidgeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    /// Единственная app-wide VM — авторизация. Остальные создаются локально по вью:
    /// экран владеет своим состоянием и не тянет чужое.
    @StateObject private var auth = AuthViewModel()
    @StateObject private var language = LanguageStore.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(language)
                .environment(\.theme, .warm)
                .environment(\.locale, language.locale)
                .tint(Theme.warm.terracotta)
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = NotificationDelegate.shared
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        PushService.shared.storeDeviceToken(token)
        Task { await PushService.shared.registerIfPossible() }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        // Без APNs приложение продолжает работать: напоминания просто не приходят.
        // На симуляторе это норма.
        #if DEBUG
        print("APNs registration failed: \(error.localizedDescription)")
        #endif
    }
}

/// Показываем пуш и когда приложение открыто — иначе напоминание теряется.
final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationDelegate()

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }
}
