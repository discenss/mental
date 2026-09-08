import Foundation

/// Мок клиента для превью и тестов.
///
/// Существует потому, что ViewModel'и принимают `RidgeAPIProtocol` в инициализаторе:
/// в Rhythmos каждая VM держала `RhytmosAPI.shared` напрямую, и проверить её было
/// нельзя. Здесь любую VM можно собрать с этим моком.
///
/// Собран как `final class`, а не `actor`: тестам нужен синхронный доступ к счётчикам.
final class MockAPI: RidgeAPIProtocol, @unchecked Sendable {
    // управление поведением из теста
    var dayResponse: DayResponse?
    var enrollmentsResult: [EnrollmentSummary] = []
    var journalResult: [JournalEntry] = []
    var errorToThrow: APIError?
    var closeDayResult: CloseDayResponse?

    // счётчики вызовов — чтобы проверять, что экран не дёргает бэкенд лишний раз
    private(set) var closeDayCallCount = 0
    private(set) var openDayCallCount = 0
    private(set) var submitIntakeCallCount = 0
    private(set) var lastIntakeAnswers: [Int: Int] = [:]
    private(set) var lastSelfcheckAnswers: [Int: Int] = [:]
    private(set) var lastSelfcheckMorning: [Int: Int] = [:]
    private(set) var updateSettingsCallCount = 0

    private func checkError() throws {
        if let errorToThrow { throw errorToThrow }
    }

    // MARK: - Авторизация

    func signInWithApple(identityToken: String, language: String,
                         timezone: String?) async throws -> AuthResponse {
        try checkError()
        return AuthResponse(accessToken: "mock-token", tokenType: "bearer",
                            expiresAt: nil, userId: 1, language: language)
    }

    func signInWithGoogle(idToken: String, language: String,
                          timezone: String?) async throws -> AuthResponse {
        try checkError()
        return AuthResponse(accessToken: "mock-token", tokenType: "bearer",
                            expiresAt: nil, userId: 1, language: language)
    }

    func me() async throws -> MeResponse {
        try checkError()
        return MeResponse(userId: 1, language: "ru", timezone: "Europe/Riga",
                          providers: ["ios"])
    }

    func redeemLinkCode(_ code: String) async throws -> LinkResult {
        try checkError()
        return LinkResult(userId: 1, merged: true)
    }

    // MARK: - Каталог

    func modules(lang: String) async throws -> [ModuleSummary] {
        try checkError()
        return MockAPI.sampleModules
    }

    func intake(lang: String) async throws -> IntakeResponse {
        try checkError()
        return try MockAPI.decode(MockAPI.intakeJSON)
    }

    func submitIntake(answers: [Int: Int]) async throws -> IntakeResult {
        try checkError()
        submitIntakeCallCount += 1
        lastIntakeAnswers = answers
        return try MockAPI.decode(#"{"leading":"BOUND","focus1":"ANX","focus2":"SELF","is_soft":false,"recommended_module":"BOUND","text":"Ведущая тема — личные границы."}"#)
    }

    // MARK: - Программы

    func enrollments() async throws -> [EnrollmentSummary] {
        try checkError()
        return enrollmentsResult
    }

    func enroll(moduleCode: String) async throws -> EnrollResponse {
        try checkError()
        return try MockAPI.decode(#"{"enrollment_id":1,"module":"BOUND","name":"Личные границы","mode":"normal","week":1,"day":1,"status":"active"}"#)
    }

    func abandonActive() async throws { try checkError() }

    func enrollmentStatus(eid: Int) async throws -> EnrollmentStatusResponse {
        try checkError()
        return try MockAPI.decode(#"{"module":"BOUND","name":"Личные границы","status":"active","week":2,"day":3,"mode":"normal","total_weeks":6,"total_days":7,"days_completed":10,"days_total":42,"started_at":"2026-09-01T10:00:00","weeks":[{"week":1,"zone":"GREEN"}]}"#)
    }

    // MARK: - День

    func daySteps(eid: Int) async throws -> DayResponse {
        try checkError()
        if let dayResponse { return dayResponse }
        return try MockAPI.decode(MockAPI.morningDayJSON)
    }

    func openDay(eid: Int) async throws -> OpenDayResponse {
        try checkError()
        openDayCallCount += 1
        return OpenDayResponse(session: .evening, week: 1, day: 1)
    }

    func closeDay(eid: Int, taskStatus: TaskStatus?, taskAnswer: String?,
                  quizAnswer: String?, reflection: [String]) async throws -> CloseDayResponse {
        try checkError()
        closeDayCallCount += 1
        if let closeDayResult { return closeDayResult }
        return try MockAPI.decode(#"{"status":"active","week":1,"day":2}"#)
    }

    // MARK: - Самопроверка

    func selfcheckQuestions(eid: Int) async throws -> SelfcheckQuestions {
        try checkError()
        return try MockAPI.decode(MockAPI.selfcheckJSON)
    }

    func submitSelfcheck(eid: Int, answers: [Int: Int], morning: [Int: Int],
                         evening: [Int: Int]) async throws -> SelfcheckResult {
        try checkError()
        lastSelfcheckAnswers = answers
        lastSelfcheckMorning = morning
        return try MockAPI.decode(#"{"zone":"GREEN","week":1,"user_text":"Неделя прошла ровно.","recommendation":"Продолжайте в том же темпе.","criticals":[]}"#)
    }

    // MARK: - Путь

    func weekInsight(eid: Int) async throws -> InsightResponse {
        try checkError()
        return InsightResponse(enabled: true, text: "Разбор недели.")
    }

    func programInsight(eid: Int) async throws -> InsightResponse {
        try checkError()
        return InsightResponse(enabled: true, text: "Итог маршрута.")
    }

    func finalProducts() async throws -> [FinalProductItem] {
        try checkError()
        return []
    }

    // MARK: - Дневник

    func journal(moduleCode: String?) async throws -> [JournalEntry] {
        try checkError()
        return journalResult
    }

    func addNote(_ text: String, moduleCode: String?) async throws { try checkError() }

    // MARK: - Прочее

    func askAI(question: String, context: String?) async throws -> AskAIResponse {
        try checkError()
        return AskAIResponse(enabled: true, text: "Мягкий ответ.", answer: nil)
    }

    func resolveAudio(code: String, lang: String) async throws -> AudioResolve {
        try checkError()
        return AudioResolve(code: code, title: "Практика", language: lang,
                            mime: "audio/mpeg", url: nil, fallback: false)
    }

    func audioFileURL(code: String, lang: String) -> URL? {
        URL(string: "https://example.invalid/\(code)")
    }

    func updateSettings(slot: String?, hour: Int?, minute: Int?,
                        timezone: String?, language: String?) async throws {
        try checkError()
        updateSettingsCallCount += 1
    }

    func registerDevice(token: String, sandbox: Bool, language: String?) async throws {
        try checkError()
    }

    func unregisterDevice(token: String) async throws { try checkError() }

    // MARK: - Данные для превью

    private static func decode<T: Decodable>(_ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    static let sampleModules: [ModuleSummary] = {
        (try? decode(#"[{"code":"BOUND","name":"Личные границы","subtitle":null,"content_version":"1.0.0","passport":{"name":"Личные границы","intro":"Про то, как перестать соглашаться быстрее, чем успеваете подумать.","for_whom":["Вам трудно говорить «нет»","Вы часто соглашаетесь и потом жалеете"],"extra_support":null,"why":null,"what_user_gets":["Личный протокол границ"],"main_result":null,"important":"Это самостоятельный маршрут, а не терапия."}},{"code":"REAL","name":"Найти себя и вернуть смысл","subtitle":null,"content_version":"1.0.0","passport":null}]"#)) ?? []
    }()

    /// Утренняя сессия: фокус + задание + аудио — как отдаёт `/day-steps`.
    static let morningDayJSON = #"""
    {"status":"active","done_today":false,"session":"morning","week":1,"day":1,
     "day_title":"Замечать автоматическое согласие",
     "week_intro":{"title":"Неделя 1","intro_screen":"На этой неделе мы учимся замечать.","meaning":null,"goal":"Заметить моменты автоматического «да»","result":"Вы начнёте различать","key_themes":["Автоматизм","Пауза"]},
     "steps":[
       {"kind":"focustask","role":"morning","focus":"Сегодня важно начать замечать моменты, когда вы соглашаетесь быстрее, чем успеваете подумать.","task":{"text":"Отметьте три ситуации за день.","subtasks":["Где было легко","Где не получилось","Что почувствовали"]},"asks_status":false,"text":"📌 <b>Фокус дня</b>\n…"},
       {"kind":"audio","code":"AUDIO_BOUND_W1_A1","title":"Практика первой недели"}
     ]}
    """#

    /// Вечерняя сессия: статус задания, квиз, три рефлексии.
    static let eveningDayJSON = #"""
    {"status":"active","done_today":false,"session":"evening","week":1,"day":1,
     "day_title":"Замечать автоматическое согласие",
     "steps":[
       {"kind":"focustask","role":"evening","focus":null,"task":{"text":"Отметьте три ситуации за день.","subtasks":[]},"asks_status":true,"status_options":["DONE","PARTIAL","NOT_DONE"],"text":"📝 …"},
       {"kind":"quiz","question":"Что было заметнее всего?","options":["Автоматическое да","Пауза перед ответом","Ничего особенного"],"text":"Что было заметнее всего?"},
       {"kind":"free_text","prompt":"Что вы заметили за собой сегодня?","text":"Что вы заметили за собой сегодня?"},
       {"kind":"free_text","prompt":"Где было труднее всего?","text":"Где было труднее всего?"},
       {"kind":"free_text","prompt":"Что хотите взять в завтрашний день?","text":"Что хотите взять в завтрашний день?"}
     ]}
    """#

    static let intakeJSON = #"""
    {"version":"1.0","client_intro":"Это 30 коротких вопросов. Здесь нет правильных ответов — ориентируйтесь на последние 2–4 недели. Результат не является диагнозом.",
     "answer_scale":[{"value":0,"text":"совсем не про меня"},{"value":1,"text":"редко бывает"},{"value":2,"text":"иногда бывает"},{"value":3,"text":"часто про меня"},{"value":4,"text":"почти всегда про меня"}],
     "start_button":"Начать",
     "questions":[{"n":1,"direction":"BOUND","text":"Мне трудно сказать «нет», даже когда я не хочу соглашаться."},{"n":2,"direction":"ANX","text":"Я часто ловлю себя на беспокойстве без явной причины."}]}
    """#

    static let selfcheckJSON = #"""
    {"week":1,
     "questions":[{"q":1,"question":"Насколько регулярно получалось заниматься?","options":["Почти каждый день","Через день","Пару раз","Почти не получалось"]}],
     "morning_markers":[{"idx":1,"question":"Как вы обычно входили в день?","options":["Спокойно","Скорее спокойно","Скорее напряжённо","Напряжённо"]}],
     "evening_markers":[{"idx":1,"question":"Как складывались дни?","options":["Ровно","Скорее ровно","Скорее трудно","Трудно"]}]}
    """#
}
