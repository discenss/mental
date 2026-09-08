import SwiftUI

/// Корневая маршрутизация: приветствие → вход → онбординг → приложение.
struct RootView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @Environment(\.theme) private var t

    var body: some View {
        Group {
            switch auth.state {
            case .loading:
                LoadingScreen()
            case .needsWelcome:
                WelcomeView { auth.completeWelcome() }
            case .unauthenticated:
                AuthView()
            case .needsOnboarding:
                OnboardingView { auth.completeOnboarding() }
            case .ready:
                MainTabView()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: auth.state)
        .task { await auth.restoreSession() }
    }
}

struct LoadingScreen: View {
    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()
            VStack(spacing: t.spacing.l) {
                ProgressView().tint(t.terracotta)
                Text("common.loading")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkDim)
            }
        }
    }
}

#Preview("Загрузка") {
    LoadingScreen()
}
