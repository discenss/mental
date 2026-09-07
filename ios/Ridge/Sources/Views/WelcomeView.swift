import SwiftUI

/// Первый экран. Оговорка «не ставим диагнозов» здесь обязательна — она есть на
/// первом экране бота, и каналы должны говорить одно и то же (§16).
struct WelcomeView: View {
    let onStart: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                VStack(spacing: t.spacing.xl) {
                    Image(systemName: "mountain.2")
                        .font(.system(size: 44, weight: .ultraLight))
                        .foregroundStyle(t.terracotta)
                        .accessibilityHidden(true)

                    VStack(spacing: t.spacing.m) {
                        Text("welcome.title")
                            .font(t.font.displaySerif(26))
                            .foregroundStyle(t.ink)
                            .multilineTextAlignment(.center)

                        Text("welcome.subtitle")
                            .font(t.font.body)
                            .foregroundStyle(t.inkMuted)
                            .multilineTextAlignment(.center)
                    }
                }
                .padding(.horizontal, t.spacing.xl)
                .slideUp()

                Spacer()

                VStack(spacing: t.spacing.l) {
                    Text("welcome.disclaimer")
                        .font(t.font.caption)
                        .foregroundStyle(t.inkDim)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)

                    AccentButton(title: "welcome.start", action: onStart)
                }
                .padding(.horizontal, t.spacing.xl)
                .padding(.bottom, t.spacing.xxl)
            }
        }
    }
}

#Preview {
    WelcomeView {}
        .environment(\.theme, .warm)
}

#Preview("Тёмная") {
    WelcomeView {}
        .environment(\.theme, .warm)
        .preferredColorScheme(.dark)
}
