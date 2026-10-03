import SwiftUI

/// Текстовая практика дня — самостоятельная сущность, параллельная аудио (см. `AudioCard`):
/// своя запись в БД (`text_assets`/`text_variants`), свой `day_range`, может быть
/// вместе с аудио дня, вместо него или не быть вовсе.
///
/// Тело приходит целиком с `/text/{code}/resolve` — в отличие от аудио, файла нет.
struct TextCard: View {
    let eid: Int
    let code: String
    let title: String?

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t
    @State private var practiceBody: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        PageCard {
            VStack(alignment: .leading, spacing: t.spacing.m) {
                HStack {
                    LabelTag(text: L10n("today.text").text, color: t.sage)
                    Spacer()
                    if isLoading {
                        ProgressView().tint(t.terracotta)
                    }
                }

                Text(title ?? code)
                    .font(t.font.bodyEmphasized)
                    .foregroundStyle(t.ink)

                if let practiceBody {
                    Text(practiceBody)
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                } else if let errorMessage {
                    Text(errorMessage)
                        .font(t.font.caption)
                        .foregroundStyle(t.inkDim)
                }

                MarkPracticeButton(eid: eid, kind: "text", code: code, title: title)
            }
        }
        .task {
            await load()
        }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let resolved = try await RidgeAPI.shared.resolveText(code: code, lang: language.current.rawValue)
            practiceBody = resolved.body
        } catch {
            errorMessage = L10n("error.notFound").text
        }
    }
}

/// Кнопка «отметить пройденным» — общая для аудио и текста: оба пишут в дневник
/// одним эндпоинтом (`POST /enrollments/{id}/practice-log`).
struct MarkPracticeButton: View {
    let eid: Int
    /// "audio" | "text" — должно совпадать с `app.services.progression.log_practice`.
    let kind: String
    let code: String
    let title: String?

    @Environment(\.theme) private var t
    @State private var isDone = false
    @State private var isLogging = false

    var body: some View {
        Button {
            Haptics.light()
            Task { await log() }
        } label: {
            Label(isDone ? doneText : markText, systemImage: isDone ? "checkmark.circle.fill" : "circle")
        }
        .font(t.font.caption)
        .foregroundStyle(isDone ? t.sage : t.terracotta)
        .disabled(isDone || isLogging)
    }

    private var doneText: String {
        kind == "audio" ? L10n("today.listened").text : L10n("today.textRead").text
    }

    private var markText: String {
        kind == "audio" ? L10n("today.markListened").text : L10n("today.markRead").text
    }

    private func log() async {
        guard !isDone, !isLogging else { return }
        isLogging = true
        defer { isLogging = false }
        do {
            try await RidgeAPI.shared.logPractice(eid: eid, kind: kind, code: code, title: title)
            isDone = true
            Haptics.success()
        } catch {
            Haptics.error()
        }
    }
}

#Preview {
    TextCard(eid: 1, code: "TEXT_BOUND_W1_T1", title: "Текстовая практика недели")
        .padding()
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
        .background(Theme.warm.paper)
}
