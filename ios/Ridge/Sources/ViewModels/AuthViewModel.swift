import AuthenticationServices
import Foundation
import SwiftUI

/// Состояние маршрутизации приложения.
///
/// Без associated values — иначе `.animation(_:value:)` на `RootView` не работает
/// (нужен `Equatable` без полезной нагрузки). Данные живут в самой VM.
enum AuthState: Equatable {
    case loading
    case needsWelcome
    case unauthenticated
    case needsOnboarding
    case ready
}

@MainActor
final class AuthViewModel: ObservableObject {
    @Published private(set) var state: AuthState = .loading
    @Published var errorMessage: String?
    /// Офлайн отделён от ошибки авторизации: сессию не рвём, показываем «нет связи».
    @Published var isOffline = false
    @Published private(set) var isBusy = false
    @Published private(set) var providers: [String] = []

    @AppStorage("ridge_seen_welcome") private var seenWelcome = false
    @AppStorage("ridge_completed_onboarding") private var completedOnboarding = false

    private let api: RidgeAPIProtocol
    private let language = LanguageStore.shared

    init(api: RidgeAPIProtocol = RidgeAPI.shared) {
        self.api = api
    }

    // MARK: - Восстановление сессии

    /// Вызывается один раз при старте.
    ///
    /// В Rhythmos любая ошибка `GET /me` роняла в `.unauthenticated` — то есть метро
    /// выглядело как разлогин. Здесь 401 (и только он) разлогинивает; сетевая ошибка
    /// оставляет сессию и показывает баннер.
    func restoreSession() async {
        guard RidgeAPI.shared.isAuthenticated else {
            state = seenWelcome ? .unauthenticated : .needsWelcome
            return
        }
        do {
            let me = try await api.me()
            providers = me.providers
            isOffline = false
            state = completedOnboarding ? .ready : .needsOnboarding
        } catch let error as APIError {
            if error.requiresSignOut {
                signOutLocally()
                state = .unauthenticated
            } else {
                // связи нет — но пользователь остаётся вошедшим
                isOffline = true
                state = completedOnboarding ? .ready : .needsOnboarding
            }
        } catch {
            isOffline = true
            state = completedOnboarding ? .ready : .needsOnboarding
        }
    }

    func completeWelcome() {
        seenWelcome = true
        state = .unauthenticated
    }

    func completeOnboarding() {
        completedOnboarding = true
        state = .ready
    }

    // MARK: - Apple Sign-In

    /// Apple обязателен в App Store, если есть другие способы входа.
    func handleAppleCompletion(_ result: Result<ASAuthorization, Error>) async {
        switch result {
        case .failure(let error):
            // отмена пользователем — не ошибка, молчим
            if (error as? ASAuthorizationError)?.code == .canceled { return }
            errorMessage = error.localizedDescription
        case .success(let auth):
            guard
                let credential = auth.credential as? ASAuthorizationAppleIDCredential,
                let tokenData = credential.identityToken,
                let identityToken = String(data: tokenData, encoding: .utf8)
            else {
                errorMessage = L10n("error.unauthorized").text
                return
            }
            await signIn { [language] in
                try await self.api.signInWithApple(
                    identityToken: identityToken,
                    language: language.current.rawValue,
                    timezone: TimeZone.current.identifier)
            }
        }
    }

    /// Google Sign-In. Токен добывает вызывающий экран через GoogleSignIn SDK —
    /// сюда приходит уже готовый `id_token`, чтобы VM не зависела от SDK.
    func signInWithGoogle(idToken: String) async {
        await signIn { [language] in
            try await self.api.signInWithGoogle(
                idToken: idToken,
                language: language.current.rawValue,
                timezone: TimeZone.current.identifier)
        }
    }

    private func signIn(_ operation: @escaping () async throws -> AuthResponse) async {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            _ = try await operation()
            let me = try? await api.me()
            providers = me?.providers ?? []
            isOffline = false
            state = completedOnboarding ? .ready : .needsOnboarding
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Связка каналов

    /// Код из Telegram-бота: аккаунты сливаются в один, прогресс не теряется.
    func redeemLinkCode(_ code: String) async -> Bool {
        isBusy = true
        errorMessage = nil
        defer { isBusy = false }
        do {
            _ = try await api.redeemLinkCode(code)
            let me = try? await api.me()
            providers = me?.providers ?? []
            return true
        } catch let error as APIError {
            errorMessage = error.errorDescription
            return false
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    // MARK: - Выход

    func signOut() {
        signOutLocally()
        state = .unauthenticated
    }

    private func signOutLocally() {
        RidgeAPI.shared.clearSession()
        providers = []
        completedOnboarding = false
    }

    /// Реакция на 401 из любого экрана: сессия недействительна — на вход.
    func handleUnauthorized() {
        signOut()
    }
}
