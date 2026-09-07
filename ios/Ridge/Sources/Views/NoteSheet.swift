import SwiftUI

/// Личная заметка в дневник. Сохранение добровольно (§8) — это предложение, а не
/// условие завершения дня.
struct NoteSheet: View {
    let onSave: (String) -> Void

    @Environment(\.theme) private var t
    @Environment(\.dismiss) private var dismiss

    @State private var text = ""

    var body: some View {
        NavigationStack {
            ZStack {
                t.paper.ignoresSafeArea()
                VStack(alignment: .leading, spacing: t.spacing.l) {
                    VoiceTextEditor(text: $text, placeholder: "journal.notePlaceholder")
                    Spacer()
                }
                .padding(t.spacing.xl)
            }
            .navigationTitle(Text("journal.noteTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("common.save") {
                        onSave(text)
                        Haptics.success()
                        dismiss()
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}

/// «Спросить ИИ» — свободный вопрос с мягким ответом.
/// Это поддержка внутри маршрута, а не консультация: оговорка обязательна.
struct AskAIView: View {
    var context: String?

    @Environment(\.theme) private var t
    @Environment(\.dismiss) private var dismiss

    @State private var question = ""
    @State private var answer: String?
    @State private var isLoading = false
    @State private var error: APIError?

    var body: some View {
        NavigationStack {
            ZStack {
                t.paper.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: t.spacing.l) {
                        VoiceTextEditor(text: $question, placeholder: "ai.placeholder")

                        AccentButton(title: "ai.send",
                                     isLoading: isLoading,
                                     isDisabled: question.trimmingCharacters(
                                        in: .whitespacesAndNewlines).isEmpty) {
                            Task { await ask() }
                        }

                        if let error {
                            ErrorBanner(error: error)
                        }

                        if let answer {
                            PageCard {
                                Text(answer)
                                    .font(t.font.body)
                                    .foregroundStyle(t.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .slideUp()
                        }

                        Text("ai.hint")
                            .font(t.font.caption)
                            .foregroundStyle(t.inkDim)
                    }
                    .padding(t.spacing.xl)
                }
            }
            .navigationTitle(Text("ai.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.close") { dismiss() }
                }
            }
        }
    }

    private func ask() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let response = try await RidgeAPI.shared.askAI(question: question, context: context)
            if response.enabled == false {
                answer = L10n("ai.disabled").text
            } else {
                answer = response.message
            }
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }
}

#Preview("Заметка") {
    NoteSheet { _ in }
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}

#Preview("Спросить ИИ") {
    AskAIView(context: nil)
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
