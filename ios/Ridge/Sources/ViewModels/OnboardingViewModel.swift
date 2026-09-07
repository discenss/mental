import Foundation
import SwiftUI

@MainActor
final class OnboardingViewModel: ObservableObject {
    enum Step: Int, CaseIterable {
        case language
        case intro
        case intake
        case result
        case reminders
    }

    @Published var step: Step = .language
    @Published private(set) var intake: IntakeResponse?
    @Published private(set) var result: IntakeResult?
    @Published private(set) var modules: [ModuleSummary] = []

    /// Ответы интейка: номер вопроса → 0…4.
    @Published var answers: [Int: Int] = [:]
    @Published var questionIndex = 0

    @Published var reminderMorning = DateComponents(hour: 10, minute: 0)
    @Published var reminderAfternoon = DateComponents(hour: 14, minute: 0)
    @Published var reminderEvening = DateComponents(hour: 20, minute: 0)

    @Published private(set) var isLoading = false
    @Published var error: APIError?

    private let api: RidgeAPIProtocol
    private let language: LanguageStore
    private var loadTask: Task<Void, Never>?

    init(api: RidgeAPIProtocol = RidgeAPI.shared, language: LanguageStore = .shared) {
        self.api = api
        self.language = language
    }

    deinit { loadTask?.cancel() }

    var questions: [IntakeQuestion] { intake?.questions ?? [] }
    var scale: [IntakeScaleOption] { intake?.answerScale ?? IntakeScaleOption.fallback }

    var currentQuestion: IntakeQuestion? {
        questions.indices.contains(questionIndex) ? questions[questionIndex] : nil
    }

    var isLastQuestion: Bool { questionIndex >= questions.count - 1 }

    /// Ответ на текущий вопрос выбран — можно идти дальше.
    var canAdvanceQuestion: Bool {
        guard let q = currentQuestion else { return false }
        return answers[q.n] != nil
    }

    /// Рекомендованная программа, если она реализована. Направлений 10, программ пока 2 —
    /// для остальных бэкенд рекомендации не даст, и это нормально.
    var recommendedModule: ModuleSummary? {
        guard let code = result?.recommendedModule?.uppercased() else { return nil }
        return modules.first { $0.code.uppercased() == code }
    }

    // MARK: - Загрузка

    func loadIntake() {
        loadTask?.cancel()
        loadTask = Task { [weak self] in
            guard let self else { return }
            await self.performLoad()
        }
    }

    private func performLoad() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            async let intakeCall = api.intake(lang: language.current.rawValue)
            async let modulesCall = api.modules(lang: language.current.rawValue)
            intake = try await intakeCall
            modules = try await modulesCall
        } catch is CancellationError {
            return
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }

    // MARK: - Ответы

    func answer(_ value: Int, for question: IntakeQuestion) {
        // клиентская валидация: значение вне 0..4 даёт на бэкенде HTTP 500
        answers[question.n] = min(max(value, 0), 4)
    }

    func nextQuestion() {
        guard !isLastQuestion else { return }
        questionIndex += 1
    }

    func previousQuestion() {
        guard questionIndex > 0 else { return }
        questionIndex -= 1
    }

    // MARK: - Отправка

    func submitIntake() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            // Пропущенные вопросы бэкенд молча считает нулями. Досылаем явные нули,
            // чтобы «не ответил» и «ответил 0» не смешивались молча на сервере.
            var payload = answers
            for q in questions where payload[q.n] == nil {
                payload[q.n] = 0
            }
            result = try await api.submitIntake(answers: payload)
            step = .result
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }

    func enroll(in moduleCode: String) async -> Bool {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            _ = try await api.enroll(moduleCode: moduleCode)
            step = .reminders
            return true
        } catch let e as APIError {
            error = e
            return false
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
            return false
        }
    }

    /// Слоты сохраняются по одному за вызов — так устроен эндпоинт.
    func saveReminders() async {
        isLoading = true
        defer { isLoading = false }
        let slots: [(String, DateComponents)] = [
            ("morning", reminderMorning),
            ("afternoon", reminderAfternoon),
            ("evening", reminderEvening),
        ]
        for (slot, time) in slots {
            try? await api.updateSettings(slot: slot, hour: time.hour, minute: time.minute,
                                          timezone: TimeZone.current.identifier,
                                          language: language.current.rawValue)
        }
        // разрешение на пуши спрашиваем ПОСЛЕ того, как человек выбрал время:
        // так системный диалог появляется осмысленно, а не в вакууме
        await PushService.shared.requestAuthorization()
        await PushService.shared.registerIfPossible()
    }
}
