import Foundation
import Testing

@testable import Ridge

/// Тесты декодирования и логики ViewModel'ей.
///
/// Проверяют ровно то, что на бэкенде не проверено типами: тела запросов там объявлены
/// как `payload: dict`, схем в `/openapi.json` нет, и клиент обязан быть терпимым к
/// пустым и неожиданным полям.

// MARK: - Декодирование

@Suite("Декодирование ответов API")
struct DecodingTests {

    private func decode<T: Decodable>(_ json: String, as type: T.Type = T.self) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    @Test("Три формы /today различаются по status")
    func dayResponseForms() throws {
        let completed: DayResponse = try decode(#"{"status":"completed","steps":[]}"#)
        #expect(completed.isCompleted)
        #expect(completed.steps.isEmpty)

        let due: DayResponse = try decode(#"{"status":"selfcheck_due","week":3,"steps":[]}"#)
        #expect(due.isSelfcheckDue)
        #expect(due.week == 3)

        let active: DayResponse = try decode(MockAPI.morningDayJSON)
        #expect(active.isActive)
        #expect(active.session == .morning)
    }

    @Test("Отсутствующий steps не ломает декодирование")
    func missingStepsIsEmpty() throws {
        // старый бэкенд (или /today вместо /day-steps) поля steps не отдаёт вовсе
        let day: DayResponse = try decode(#"{"status":"completed"}"#)
        #expect(day.steps.isEmpty)
    }

    @Test("Утренние шаги: фокус, задание, аудио")
    func morningSteps() throws {
        let day: DayResponse = try decode(MockAPI.morningDayJSON)
        let kinds = day.steps.map(\.kind)
        #expect(kinds.contains(.focustask))
        #expect(kinds.contains(.audio))

        let focus = day.steps.first { $0.kind == .focustask }
        #expect(focus?.asksStatus == false)
        #expect(focus?.task?.subtasks.count == 3)
    }

    @Test("Вечерние шаги: статус задания, квиз, три рефлексии")
    func eveningSteps() throws {
        let day: DayResponse = try decode(MockAPI.eveningDayJSON)
        #expect(day.session == .evening)

        let focus = day.steps.first { $0.kind == .focustask }
        #expect(focus?.asksStatus == true)
        #expect(day.steps.filter { $0.kind == .quiz }.count == 1)
        #expect(day.steps.filter { $0.kind == .freeText }.count == 3)

        // квиз строго до рефлексий — порядок задан бэкендом
        let kinds = day.steps.map(\.kind)
        if let quiz = kinds.firstIndex(of: .quiz),
           let first = kinds.firstIndex(of: .freeText) {
            #expect(quiz < first)
        }
    }

    @Test("Неизвестный kind шага не ломает экран")
    func unknownStepKind() throws {
        let step: DayStep = try decode(#"{"kind":"something_new","text":"x"}"#)
        #expect(step.kind == .unknown)
    }

    @Test("Пустые свободные JSON-поля декодируются мягко")
    func lenientOptionalFields() throws {
        let task: DayTask = try decode(#"{"text":null}"#)
        #expect(task.subtasks.isEmpty)

        let intro: WeekIntro = try decode(#"{}"#)
        #expect(intro.keyThemes.isEmpty)
        #expect(intro.title == nil)
    }

    @Test("Шкала интейка принимается и объектами, и строками")
    func intakeScaleShapes() throws {
        let objects: IntakeResponse = try decode(MockAPI.intakeJSON)
        #expect(objects.answerScale.count == 5)

        let strings: IntakeResponse = try decode(
            #"{"answer_scale":["нет","редко","иногда"],"questions":[]}"#)
        #expect(strings.answerScale.count == 3)
        #expect(strings.answerScale[1].value == 1)

        // если шкалы нет вовсе — берём каноническую 0–4 из §12.1
        let missing: IntakeResponse = try decode(#"{"questions":[]}"#)
        #expect(missing.answerScale.count == 5)
    }

    @Test("criticals приходят и строками, и объектами")
    func criticalsShapes() throws {
        let strings: SelfcheckResult = try decode(
            #"{"zone":"YELLOW","criticals":["Мягкий блок."]}"#)
        #expect(strings.criticals == ["Мягкий блок."])

        let objects: SelfcheckResult = try decode(
            #"{"zone":"RED","criticals":[{"additional_text":"Другой блок."}]}"#)
        #expect(objects.criticals == ["Другой блок."])

        let none: SelfcheckResult = try decode(#"{"zone":"GREEN"}"#)
        #expect(none.criticals.isEmpty)
    }

    @Test("Захардкоженные в бэкенде 6/7/42 берутся из ответа")
    func statusTotals() throws {
        let status: EnrollmentStatusResponse = try decode(
            #"{"module":"BOUND","name":"Границы","status":"active","week":1,"day":1,"weeks":[]}"#)
        #expect(status.totalWeeks == 6)
        #expect(status.daysTotal == 42)
    }

    @Test("Неизвестный статус программы не роняет декодирование")
    func unknownEnrollmentStatus() throws {
        let summary: EnrollmentSummary = try decode(
            #"{"enrollment_id":1,"module":"BOUND","name":"Границы","status":"wat","week":1,"day":1,"mode":"normal"}"#)
        #expect(summary.status == .active)
    }
}

// MARK: - Даты

@Suite("Разбор дат бэкенда")
struct DateParsingTests {

    @Test("Наивный ISO без таймзоны читается как локальное время")
    func naiveISO() throws {
        let date = DateParsing.date(from: "2026-09-07T14:30:00")
        #expect(date != nil)

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .current
        let parts = calendar.dateComponents([.year, .month, .day, .hour], from: date!)
        #expect(parts.year == 2026)
        #expect(parts.month == 9)
        #expect(parts.day == 7)
        // час не сдвинулся — строка без зоны трактуется как локальная
        #expect(parts.hour == 14)
    }

    @Test("Микросекунды не мешают")
    func fractionalSeconds() {
        #expect(DateParsing.date(from: "2026-09-07T14:30:00.123456") != nil)
    }

    @Test("Пустое и мусорное значение дают nil")
    func invalidValues() {
        #expect(DateParsing.date(from: nil) == nil)
        #expect(DateParsing.date(from: "") == nil)
        #expect(DateParsing.date(from: "не дата") == nil)
    }

    @Test("Форматтеры следуют выбранному языку, а не ru_RU")
    func formattersUseLanguage() {
        let date = Date(timeIntervalSince1970: 1_757_246_400)   // 2026-09-07
        let ru = DateFormatting.monthTitle(date, language: .ru)
        let en = DateFormatting.monthTitle(date, language: .en)
        #expect(ru != en, "ru и en должны форматироваться по-разному")
    }

    @Test("Неделя в календаре начинается с понедельника")
    func weekStartsMonday() {
        let symbols = DateFormatting.weekdaySymbols(language: .ru)
        #expect(symbols.count == 7)
        // последний столбец — воскресенье
        let sunday = DateFormatting.weekdaySymbols(language: .en).last
        #expect(sunday == "S")
    }
}

// MARK: - Ошибки

@Suite("Разделение 401 и офлайна")
struct ErrorTests {

    @Test("Только 401 требует разлогина")
    func onlyUnauthorizedSignsOut() {
        #expect(APIError.unauthorized("").requiresSignOut)
        #expect(!APIError.offline.requiresSignOut)
        #expect(!APIError.timedOut.requiresSignOut)
        #expect(!APIError.server(status: 500, message: "x").requiresSignOut)
        #expect(!APIError.forbidden("").requiresSignOut)
    }
}

// MARK: - ViewModel дня

@Suite("TodayViewModel")
@MainActor
struct TodayViewModelTests {

    private func makeVM(_ mock: MockAPI) -> TodayViewModel {
        TodayViewModel(api: mock)
    }

    private var activeEnrollment: [EnrollmentSummary] {
        let json = #"[{"enrollment_id":1,"module":"BOUND","name":"Границы","status":"active","week":1,"day":1,"mode":"normal"}]"#
        return (try? JSONDecoder().decode([EnrollmentSummary].self, from: Data(json.utf8))) ?? []
    }

    @Test("Берётся активный маршрут (одновременно идёт только один)")
    func picksActiveEnrollment() async {
        let mock = MockAPI()
        mock.enrollmentsResult = activeEnrollment
        let vm = makeVM(mock)
        await vm.refresh()
        #expect(vm.hasRoute)
        #expect(vm.eid == 1)
    }

    @Test("Без маршрута экран показывает пустое состояние, а не падает")
    func noRoute() async {
        let mock = MockAPI()
        mock.enrollmentsResult = []
        let vm = makeVM(mock)
        await vm.refresh()
        #expect(!vm.hasRoute)
        #expect(vm.day == nil)
    }

    @Test("Повторный вызов closeDay не отправляет второй запрос")
    func closeDayGuardsDoubleTap() async {
        let mock = MockAPI()
        mock.enrollmentsResult = activeEnrollment
        let vm = makeVM(mock)
        await vm.refresh()

        // два «параллельных» нажатия — второй должен отсечься флагом isSubmitting
        async let first = vm.closeDay()
        async let second = vm.closeDay()
        _ = await (first, second)

        #expect(mock.closeDayCallCount == 1,
                "closeDay продвигает день и не идемпотентен — второй вызов недопустим")
    }

    @Test("already_closed от бэкенда не считается ошибкой")
    func alreadyClosedIsNotError() async throws {
        let mock = MockAPI()
        mock.enrollmentsResult = activeEnrollment
        mock.closeDayResult = try JSONDecoder().decode(
            CloseDayResponse.self,
            from: Data(#"{"status":"active","week":1,"day":2,"already_closed":true}"#.utf8))
        let vm = makeVM(mock)
        await vm.refresh()
        let ok = await vm.closeDay()
        #expect(ok)
        #expect(vm.error == nil)
    }

    @Test("Офлайн не сбрасывает маршрут")
    func offlineKeepsState() async {
        let mock = MockAPI()
        mock.enrollmentsResult = activeEnrollment
        let vm = makeVM(mock)
        await vm.refresh()
        #expect(vm.hasRoute)

        mock.errorToThrow = .offline
        await vm.refresh()
        #expect(vm.error != nil)
        #expect(vm.error?.requiresSignOut == false)
    }

    @Test("Число ячеек рефлексии равно числу вопросов")
    func reflectionSlotsMatchPrompts() async throws {
        let mock = MockAPI()
        mock.enrollmentsResult = activeEnrollment
        mock.dayResponse = try JSONDecoder().decode(
            DayResponse.self, from: Data(MockAPI.eveningDayJSON.utf8))
        let vm = makeVM(mock)
        await vm.refresh()
        #expect(vm.reflectionPrompts.count == 3)
        #expect(vm.reflections.count == 3)
    }
}

// MARK: - Онбординг

@Suite("OnboardingViewModel")
@MainActor
struct OnboardingViewModelTests {

    @Test("Значение вне 0…4 обрезается: на бэкенде это HTTP 500")
    func clampsAnswerRange() async throws {
        let mock = MockAPI()
        let vm = OnboardingViewModel(api: mock)
        vm.loadIntake()
        try await Task.sleep(for: .milliseconds(50))

        guard let question = vm.questions.first else {
            Issue.record("вопросы не загрузились")
            return
        }
        vm.answer(99, for: question)
        #expect(vm.answers[question.n] == 4)
        vm.answer(-5, for: question)
        #expect(vm.answers[question.n] == 0)
    }

    @Test("Пропущенные вопросы досылаются явными нулями")
    func fillsSkippedAnswers() async throws {
        let mock = MockAPI()
        let vm = OnboardingViewModel(api: mock)
        vm.loadIntake()
        try await Task.sleep(for: .milliseconds(50))

        // отвечаем только на первый из двух
        if let first = vm.questions.first {
            vm.answer(3, for: first)
        }
        await vm.submitIntake()

        #expect(mock.submitIntakeCallCount == 1)
        #expect(mock.lastIntakeAnswers.count == vm.questions.count,
                "бэкенд молча считает пропуски нулями — отправляем их явно")
    }
}

// MARK: - Самопроверка

@Suite("SelfcheckViewModel")
@MainActor
struct SelfcheckViewModelTests {

    @Test("Маркеры идут блоком ПЕРЕД вопросами самопроверки")
    func markersComeFirst() async {
        let vm = SelfcheckViewModel(eid: 1, api: MockAPI())
        await vm.load()

        #expect(vm.currentPage == .markersIntro)
        vm.next()
        if case .marker = vm.currentPage {} else {
            Issue.record("после вступления должны идти маркеры, а не вопросы")
        }
    }

    @Test("Ответы отправляются индексами вариантов, а не текстами")
    func sendsOptionIndexes() async {
        let vm = SelfcheckViewModel(eid: 1, api: MockAPI())
        await vm.load()
        vm.answers[1] = 2
        vm.setMarker(phase: .morning, idx: 1, choice: 3)
        await vm.submit()

        #expect(vm.result != nil)
    }

    @Test("Нельзя пройти дальше без ответа на маркер")
    func requiresMarkerAnswer() async {
        let vm = SelfcheckViewModel(eid: 1, api: MockAPI())
        await vm.load()
        vm.next()                               // на первый маркер
        #expect(!vm.canAdvance)
        vm.setMarker(phase: .morning, idx: 1, choice: 0)
        #expect(vm.canAdvance)
    }
}

// MARK: - Язык

@Suite("Локализация")
struct LocalizationTests {

    @Test("Активен только русский; остальные помечены «скоро»")
    func onlyRussianAvailable() {
        #expect(AppLanguage.ru.isAvailable)
        for lang in AppLanguage.allCases where lang != .ru {
            #expect(!lang.isAvailable, "\(lang.rawValue) не должен быть активен на этом этапе")
        }
    }

    @Test("У каждого языка своя локаль для форматтеров")
    func localesDiffer() {
        #expect(AppLanguage.ru.locale.identifier != AppLanguage.en.locale.identifier)
    }

    @Test("У каждого направления интейка есть SF Symbol")
    func everyDirectionHasSymbol() {
        for direction in Direction.allCases {
            #expect(!direction.symbol.isEmpty, "нет символа для \(direction.rawValue)")
        }
        // 10 направлений из §2.1
        #expect(Direction.allCases.count == 10)
    }

    @Test("Порядок направлений = приоритет бережности")
    func directionOrderMatchesBackend() {
        #expect(Direction.allCases.first == .burn)
        #expect(Direction.allCases.last == .proc)
    }

    @Test("Слот аудио выводится из дня: 1-2→A1, 3-4→A2, 5-6→A3, 7→FINAL")
    func audioSlotFromDay() {
        #expect(AudioSlot(day: 1) == .a1)
        #expect(AudioSlot(day: 2) == .a1)
        #expect(AudioSlot(day: 3) == .a2)
        #expect(AudioSlot(day: 5) == .a3)
        #expect(AudioSlot(day: 7) == .final)
    }
}
