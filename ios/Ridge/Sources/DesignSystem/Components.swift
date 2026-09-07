import SwiftUI

// MARK: - AccentButton

/// Основная кнопка: во всю ширину, минимум 48pt по высоте.
struct AccentButton: View {
    let title: LocalizedStringKey
    var isLoading = false
    var isDisabled = false
    let action: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        Button {
            Haptics.light()
            action()
        } label: {
            Group {
                if isLoading {
                    ProgressView().tint(.white)
                } else {
                    Text(title)
                        .font(t.font.bodyEmphasized)
                        .foregroundStyle(isDisabled ? t.inkDim : .white)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 48)
        }
        .background(isDisabled ? t.inkWhisper.opacity(0.5) : t.terracotta)
        .clipShape(RoundedRectangle(cornerRadius: t.corners.button))
        .disabled(isDisabled || isLoading)
        .accessibilityLabel(title)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint(isLoading ? Text("common.loading") : Text(""))
    }
}

// MARK: - GhostButton

struct GhostButton: View {
    let title: LocalizedStringKey
    var icon: String?
    let action: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        Button {
            Haptics.light()
            action()
        } label: {
            HStack(spacing: t.spacing.s) {
                if let icon {
                    Image(systemName: icon).font(.system(size: 15))
                }
                Text(title).font(t.font.body)
            }
            .foregroundStyle(t.terracotta)
            .frame(maxWidth: .infinity, minHeight: 48)
            .overlay(
                RoundedRectangle(cornerRadius: t.corners.button)
                    .strokeBorder(t.terracotta, lineWidth: 1)
            )
        }
        .accessibilityLabel(title)
        .accessibilityAddTraits(.isButton)
    }
}

// MARK: - PillBadge

struct PillBadge: View {
    let text: String
    var color: Color = Theme.warm.terracotta

    @Environment(\.theme) private var t

    var body: some View {
        Text(text)
            .font(t.font.caption)
            .foregroundStyle(color)
            .padding(.horizontal, t.spacing.m)
            .padding(.vertical, t.spacing.xs)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}

// MARK: - LabelTag

/// 11pt uppercase tracked — заголовок секции.
struct LabelTag: View {
    let text: String
    var color: Color = Theme.warm.inkMuted

    var body: some View {
        Text(text)
            .labelUppercase()
            .foregroundStyle(color)
            .accessibilityAddTraits(.isHeader)
    }
}

// MARK: - InlineSerifQuote

struct InlineSerifQuote: View {
    let text: String

    @Environment(\.theme) private var t

    var body: some View {
        Text(text)
            .font(t.font.bodySerif)
            .foregroundStyle(t.inkMuted)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - ProgressDashes

/// Индикатор шагов: капсулы 3pt.
struct ProgressDashes: View {
    let total: Int
    let current: Int
    var activeColor: Color = Theme.warm.terracotta
    var inactiveColor: Color = Theme.warm.inkWhisper

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<max(total, 1), id: \.self) { i in
                Capsule()
                    .fill(i < current ? activeColor : inactiveColor)
                    .frame(height: 3)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text("a11y.progress \(current) \(total)"))
    }
}

// MARK: - ChoiceGlyph / SelectionMark

/// Круг 42pt с SF Symbol; при выборе заливается терракотой @0.13.
struct ChoiceGlyph: View {
    let systemName: String
    var color: Color = Theme.warm.terracotta
    var isSelected = false

    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            Circle()
                .fill(isSelected ? color.opacity(0.13) : t.paper.opacity(0.7))
                .overlay(
                    Circle().strokeBorder(color.opacity(isSelected ? 0.65 : 0.35), lineWidth: 1.2)
                )
            Image(systemName: systemName)
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(color)
        }
        .frame(width: 42, height: 42)
        .accessibilityHidden(true)          // подпись несёт родительская карточка
    }
}

struct SelectionMark: View {
    var isSelected: Bool
    var color: Color = Theme.warm.terracotta

    var body: some View {
        ZStack {
            Circle()
                .fill(isSelected ? color : .clear)
                .overlay(
                    Circle().strokeBorder(
                        isSelected ? color : Theme.warm.borderStrong.opacity(0.55),
                        lineWidth: 1.2)
                )
                .frame(width: 26, height: 26)
            if isSelected {
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - ChoiceCard

/// Карточка варианта ответа: глиф + текст + отметка выбора.
/// Используется в онбординге, квизе, маркерах и самопроверке — везде, где список вариантов.
///
/// Вариантов бывает 5, 6 и 7 (90/9/3 вопроса соответственно), поэтому это именно
/// список, а не сегментированный контрол: сегменты на 7 длинных подписей нечитаемы.
struct ChoiceCard: View {
    let text: String
    var subtitle: String?
    var icon: String?
    let isSelected: Bool
    var isDisabled = false
    let action: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        Button {
            guard !isDisabled else { return }
            Haptics.selection()
            action()
        } label: {
            HStack(alignment: .center, spacing: t.spacing.m) {
                if let icon {
                    ChoiceGlyph(systemName: icon, isSelected: isSelected)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(text)
                        .font(t.font.body)
                        .foregroundStyle(isDisabled ? t.inkDim : t.ink)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    if let subtitle {
                        Text(subtitle)
                            .font(t.font.caption)
                            .foregroundStyle(t.inkDim)
                    }
                }
                Spacer(minLength: t.spacing.s)
                SelectionMark(isSelected: isSelected)
            }
            .padding(t.spacing.l)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? t.terracotta.opacity(0.06) : t.surface)
            .clipShape(RoundedRectangle(cornerRadius: t.corners.card))
            .overlay(
                RoundedRectangle(cornerRadius: t.corners.card)
                    .strokeBorder(isSelected ? t.terracotta.opacity(0.5) : t.border,
                                  lineWidth: isSelected ? 1.2 : 0.5)
            )
        }
        .buttonStyle(.plain)
        .disabled(isDisabled)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(subtitle.map { "\(text). \($0)" } ?? text))
        .accessibilityValue(Text(isSelected ? "a11y.selected" : "a11y.notSelected"))
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }
}

// MARK: - Пустое состояние

/// Единый вид «здесь пока пусто»: иконка 36–40pt, заголовок, подпись, действие.
struct EmptyStateCard: View {
    let icon: String
    let title: LocalizedStringKey
    var message: LocalizedStringKey?
    var actionTitle: LocalizedStringKey?
    var action: (() -> Void)?

    @Environment(\.theme) private var t

    var body: some View {
        PageCard {
            VStack(spacing: t.spacing.m) {
                Image(systemName: icon)
                    .font(.system(size: 38, weight: .light))
                    .foregroundStyle(t.inkWhisper)
                    .accessibilityHidden(true)
                Text(title)
                    .font(t.font.titleS)
                    .foregroundStyle(t.ink)
                    .multilineTextAlignment(.center)
                if let message {
                    Text(message)
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let actionTitle, let action {
                    AccentButton(title: actionTitle, action: action)
                        .padding(.top, t.spacing.xs)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, t.spacing.s)
        }
    }
}

// MARK: - Показ ошибки

/// Полоска с ошибкой. Офлайн подаётся мягче сбоя: сессия цела, данные не потеряны.
struct ErrorBanner: View {
    let error: APIError
    var retry: (() -> Void)?

    @Environment(\.theme) private var t

    private var isOffline: Bool {
        if case .offline = error { return true }
        if case .timedOut = error { return true }
        return false
    }

    var body: some View {
        HStack(alignment: .top, spacing: t.spacing.m) {
            Image(systemName: isOffline ? "wifi.slash" : "exclamationmark.triangle")
                .font(.system(size: 15))
                .foregroundStyle(isOffline ? t.inkMuted : t.safety)
                .accessibilityHidden(true)
            Text(error.errorDescription ?? "")
                .font(t.font.caption)
                .foregroundStyle(t.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if let retry {
                Button(action: retry) {
                    Text("common.retry").font(t.font.caption)
                }
                .foregroundStyle(t.terracotta)
            }
        }
        .padding(t.spacing.m)
        .background((isOffline ? t.inkWhisper : t.safety).opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: t.corners.input))
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Previews

#Preview("Кнопки") {
    VStack(spacing: 16) {
        AccentButton(title: "common.next") {}
        AccentButton(title: "common.next", isLoading: true) {}
        AccentButton(title: "common.next", isDisabled: true) {}
        GhostButton(title: "common.back", icon: "chevron.left") {}
        ProgressDashes(total: 5, current: 2)
    }
    .padding()
    .background(Theme.warm.paper)
}

#Preview("Варианты ответа") {
    VStack(spacing: 12) {
        ChoiceCard(text: "Часто про меня", icon: "wind", isSelected: true) {}
        ChoiceCard(text: "Иногда бывает", subtitle: "за последние 2–4 недели",
                   icon: "cloud.fog", isSelected: false) {}
        ChoiceCard(text: "Совсем не про меня", isSelected: false) {}
    }
    .padding()
    .background(Theme.warm.paper)
}

#Preview("Состояния") {
    ScrollView {
        VStack(spacing: 16) {
            EmptyStateCard(icon: "book.closed", title: "history.empty",
                           message: "history.emptyBody",
                           actionTitle: "history.goToday") {}
            ErrorBanner(error: .offline) {}
            ErrorBanner(error: .invalidState("Этот шаг сейчас недоступен")) {}
        }
        .padding()
    }
    .background(Theme.warm.paper)
}
