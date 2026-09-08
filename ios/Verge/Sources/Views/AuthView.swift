import AuthenticationServices
import SwiftUI

/// Вход: Apple, Google и код связи из Telegram.
///
/// Apple Sign-In обязателен для App Store, когда есть другие способы входа, поэтому
/// он первый и оформлен системной кнопкой. Google-кнопка появляется только если
/// SDK сконфигурирован — иначе она вела бы в никуда (см. `GoogleSignInBridge`).
struct AuthView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @Environment(\.theme) private var t
    @Environment(\.colorScheme) private var scheme

    @State private var showLinkSheet = false

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                VStack(spacing: t.spacing.m) {
                    Text("auth.title")
                        .font(t.font.displaySerif(24))
                        .foregroundStyle(t.ink)
                    Text("auth.subtitle")
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, t.spacing.xl)

                Spacer()

                VStack(spacing: t.spacing.m) {
                    // Ошибка ВНЕ зоны спиннера: раньше `ProgressView` висел оверлеем
                    // поверх всего стека, и сообщение о неудачном входе было не увидеть —
                    // экран выглядел так, будто «ничего не произошло».
                    if let error = auth.errorMessage {
                        ErrorBanner(error: .server(status: 0, message: error))
                            .transition(.opacity)
                    }

                    ZStack {
                        VStack(spacing: t.spacing.m) {
                            SignInWithAppleButton(.signIn) { request in
                                request.requestedScopes = [.email]
                            } onCompletion: { result in
                                Task { await auth.handleAppleCompletion(result) }
                            }
                            .signInWithAppleButtonStyle(scheme == .dark ? .white : .black)
                            .frame(height: 48)
                            .clipShape(RoundedRectangle(cornerRadius: t.corners.button))

                            if GoogleSignInBridge.isConfigured {
                                GhostButton(title: "auth.google", icon: "globe") {
                                    Task { await signInWithGoogle() }
                                }
                            }
                        }
                        // Системная `SignInWithAppleButton` не реагирует на наш `isBusy`
                        // и во время запроса выглядит просто бледной. Поэтому гасим стек
                        // сами и показываем поверх спиннер — видно, что идёт работа.
                        .opacity(auth.isBusy ? 0.35 : 1)
                        .allowsHitTesting(!auth.isBusy)

                        if auth.isBusy {
                            ProgressView()
                                .tint(t.terracotta)
                                .accessibilityLabel(Text("common.loading"))
                        }
                    }

                    Button {
                        showLinkSheet = true
                    } label: {
                        Text("auth.linkTelegram")
                            .font(t.font.caption)
                            .foregroundStyle(t.inkMuted)
                            .underline()
                    }
                    .padding(.top, t.spacing.s)
                    .disabled(auth.isBusy)
                }
                .padding(.horizontal, t.spacing.xl)
                .padding(.bottom, t.spacing.xxl)
                .animation(.easeInOut(duration: 0.2), value: auth.errorMessage)
                .animation(.easeInOut(duration: 0.2), value: auth.isBusy)
            }
        }
        .sheet(isPresented: $showLinkSheet) {
            LinkCodeSheet()
        }
    }

    private func signInWithGoogle() async {
        do {
            let idToken = try await GoogleSignInBridge.signIn()
            await auth.signInWithGoogle(idToken: idToken)
        } catch {
            auth.errorMessage = error.localizedDescription
        }
    }
}

// MARK: - Код связи

/// Ввод шестизначного кода из бота. После склейки прогресс из Telegram виден здесь.
struct LinkCodeSheet: View {
    @EnvironmentObject private var auth: AuthViewModel
    @Environment(\.theme) private var t
    @Environment(\.dismiss) private var dismiss

    @State private var code = ""
    @State private var didLink = false
    @FocusState private var focused: Bool

    private var isValid: Bool { code.count == 6 && code.allSatisfy(\.isNumber) }

    var body: some View {
        NavigationStack {
            ZStack {
                t.paper.ignoresSafeArea()

                VStack(spacing: t.spacing.xl) {
                    Text("auth.linkHint")
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                    TextField("auth.linkPlaceholder", text: $code)
                        .font(.system(size: 28, weight: .medium, design: .rounded))
                        .multilineTextAlignment(.center)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .focused($focused)
                        .padding(t.spacing.l)
                        .background(t.surface)
                        .clipShape(RoundedRectangle(cornerRadius: t.corners.input))
                        .overlay(
                            RoundedRectangle(cornerRadius: t.corners.input)
                                .strokeBorder(t.border, lineWidth: 0.5)
                        )
                        .onChange(of: code) { _, new in
                            // только цифры, максимум 6 — иначе бэкенд ответит 422
                            code = String(new.filter(\.isNumber).prefix(6))
                        }
                        .accessibilityLabel(Text("auth.linkTitle"))

                    if didLink {
                        Text("auth.linkSuccess")
                            .font(t.font.caption)
                            .foregroundStyle(t.sage)
                            .multilineTextAlignment(.center)
                    } else if let error = auth.errorMessage {
                        ErrorBanner(error: .server(status: 0, message: error))
                    }

                    AccentButton(title: "auth.linkSubmit",
                                 isLoading: auth.isBusy,
                                 isDisabled: !isValid) {
                        Task {
                            if await auth.redeemLinkCode(code) {
                                didLink = true
                                Haptics.success()
                                try? await Task.sleep(for: .seconds(1.2))
                                dismiss()
                            } else {
                                Haptics.error()
                            }
                        }
                    }

                    Spacer()
                }
                .padding(t.spacing.xl)
            }
            .navigationTitle(Text("auth.linkTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.cancel") { dismiss() }
                }
            }
            .task { focused = true }
        }
    }
}

// MARK: - Google Sign-In

/// Прослойка над GoogleSignIn SDK.
///
/// SDK подключается пакетом (`https://github.com/google/GoogleSignIn-iOS`) и требует
/// `GIDClientID` в Info.plist. Пока его нет, `isConfigured == false` и кнопка Google
/// просто не показывается — вход через Apple работает сам по себе.
///
/// Когда SDK добавлен: раскомментируйте импорт и тело `signIn()`.
enum GoogleSignInBridge {
    static var isConfigured: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String)?.isEmpty == false
    }

    enum GoogleSignInError: LocalizedError {
        case notConfigured
        case noIDToken

        var errorDescription: String? {
            switch self {
            case .notConfigured: return "Google Sign-In не настроен."
            case .noIDToken:     return "Google не вернул id_token."
            }
        }
    }

    /// Возвращает `id_token`, который бэкенд проверит по JWKS Google.
    static func signIn() async throws -> String {
        guard isConfigured else { throw GoogleSignInError.notConfigured }

        // MARK: Раскомментировать после добавления пакета GoogleSignIn-iOS
        //
        // import GoogleSignIn
        //
        // guard let root = UIApplication.shared.connectedScenes
        //     .compactMap({ $0 as? UIWindowScene })
        //     .flatMap({ $0.windows })
        //     .first(where: \.isKeyWindow)?.rootViewController
        // else { throw GoogleSignInError.notConfigured }
        //
        // let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: root)
        // guard let idToken = result.user.idToken?.tokenString else {
        //     throw GoogleSignInError.noIDToken
        // }
        // return idToken

        throw GoogleSignInError.notConfigured
    }
}

#Preview {
    AuthView()
        .environmentObject(AuthViewModel())
        .environment(\.theme, .warm)
}
