import Foundation

// MARK: - Ошибки

/// Ошибка сети/сервера.
///
/// Ключевое отличие от Rhythmos: **401 отделён от сетевого сбоя**. Там любая ошибка
/// `GET /me` роняла пользователя в `.unauthenticated`, поэтому метро или самолёт
/// выглядели как «вас разлогинили». Здесь `.unauthorized` = сессия недействительна
/// (разлогин), `.offline` = связи нет (сессию сохраняем, показываем «нет связи»).
enum APIError: LocalizedError, Sendable {
    case invalidURL
    case offline
    case timedOut
    case unauthorized(String)
    case forbidden(String)
    case notFound
    /// Бэкенд не имеет обработчиков исключений: `ValueError` в сервисах становится
    /// HTTP 500, а не 422. На `open-day`/`close-day`/`selfcheck` это означает
    /// «неверное состояние», а не поломку — трактуем отдельно.
    case invalidState(String)
    case server(status: Int, message: String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return L10n("error.invalidURL").text
        case .offline:
            return L10n("error.offline").text
        case .timedOut:
            return L10n("error.timedOut").text
        case .unauthorized(let m):
            return m.isEmpty ? L10n("error.unauthorized").text : m
        case .forbidden(let m):
            return m.isEmpty ? L10n("error.forbidden").text : m
        case .notFound:
            return L10n("error.notFound").text
        case .invalidState(let m):
            return m.isEmpty ? L10n("error.invalidState").text : m
        case .server(_, let m):
            return m
        case .decoding:
            return L10n("error.decoding").text
        }
    }

    /// Нужно ли разлогинивать пользователя. Только для 401 — сетевые сбои сессию не рвут.
    var requiresSignOut: Bool {
        if case .unauthorized = self { return true }
        return false
    }
}

// MARK: - Протокол

/// Контракт клиента. Существует, чтобы ViewModel'и можно было тестировать с моком:
/// в Rhythmos каждая VM держала `RhytmosAPI.shared` напрямую и была непроверяема.
protocol RidgeAPIProtocol: Sendable {
    // авторизация
    func signInWithApple(identityToken: String, language: String, timezone: String?) async throws -> AuthResponse
    func signInWithGoogle(idToken: String, language: String, timezone: String?) async throws -> AuthResponse
    func me() async throws -> MeResponse
    func redeemLinkCode(_ code: String) async throws -> LinkResult

    // каталог и интейк
    func modules(lang: String) async throws -> [ModuleSummary]
    func intake(lang: String) async throws -> IntakeResponse
    func submitIntake(answers: [Int: Int]) async throws -> IntakeResult

    // программы
    func enrollments() async throws -> [EnrollmentSummary]
    func enroll(moduleCode: String) async throws -> EnrollResponse
    func abandonActive() async throws
    func enrollmentStatus(eid: Int) async throws -> EnrollmentStatusResponse

    // день
    func daySteps(eid: Int) async throws -> DayResponse
    func openDay(eid: Int) async throws -> OpenDayResponse
    func closeDay(eid: Int, taskStatus: TaskStatus?, taskAnswer: String?,
                  quizAnswer: String?, reflection: [String]) async throws -> CloseDayResponse

    // самопроверка
    func selfcheckQuestions(eid: Int) async throws -> SelfcheckQuestions
    func submitSelfcheck(eid: Int, answers: [Int: Int],
                         morning: [Int: Int], evening: [Int: Int]) async throws -> SelfcheckResult

    // путь
    func weekInsight(eid: Int) async throws -> InsightResponse
    func programInsight(eid: Int) async throws -> InsightResponse
    func finalProducts() async throws -> [FinalProductItem]

    // дневник
    func journal(moduleCode: String?) async throws -> [JournalEntry]
    func addNote(_ text: String, moduleCode: String?) async throws

    // прочее
    func askAI(question: String, context: String?) async throws -> AskAIResponse
    func resolveAudio(code: String, lang: String) async throws -> AudioResolve
    func audioFileURL(code: String, lang: String) -> URL?
    func updateSettings(slot: String?, hour: Int?, minute: Int?,
                        timezone: String?, language: String?) async throws
    func registerDevice(token: String, sandbox: Bool, language: String?) async throws
    func unregisterDevice(token: String) async throws
}

// MARK: - Реализация

/// HTTP-клиент Mental API.
///
/// Ядро (пять generic-глаголов + `makeRequest`/`execute`/`apiError`) взято из Rhythmos:
/// оно обрабатывает три формы FastAPI-детали — строка, вложенный объект с `message`,
/// отсутствие. Добавлены таймауты, отмена и различение 401 от офлайна.
actor RidgeAPI: RidgeAPIProtocol {
    static let shared = RidgeAPI()

    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    /// Базовый URL из xcconfig (`RIDGE_API_BASE_URL`), с возможностью переопределить
    /// в настройках — удобно на устройстве, когда бэкенд на машине разработчика.
    nonisolated var baseURL: String {
        if let override = UserDefaults.standard.string(forKey: "ridge_base_url_override"),
           !override.isEmpty {
            return override.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        }
        let fromConfig = Bundle.main.object(forInfoDictionaryKey: "RIDGE_API_BASE_URL") as? String
        let value = (fromConfig?.isEmpty == false ? fromConfig! : "http://127.0.0.1:8000")
        return value.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    nonisolated var token: String? {
        get { Keychain.get(.accessToken) }
        set { Keychain.set(newValue, for: .accessToken) }
    }

    nonisolated var userId: Int? {
        get { Keychain.get(.userId).flatMap(Int.init) }
        set { Keychain.set(newValue.map(String.init), for: .userId) }
    }

    nonisolated var isAuthenticated: Bool { token != nil }

    nonisolated func clearSession() {
        Keychain.removeAll()
    }

    init(session: URLSession? = nil) {
        if let session {
            self.session = session
        } else {
            // В Rhythmos использовался `URLSession.shared` с дефолтами: запрос мог висеть
            // 60 секунд, и экран всё это время оставался в загрузке.
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 15
            config.timeoutIntervalForResource = 30
            config.waitsForConnectivity = false
            self.session = URLSession(configuration: config)
        }
    }

    // MARK: - Авторизация

    func signInWithApple(identityToken: String, language: String = "ru",
                         timezone: String? = TimeZone.current.identifier) async throws -> AuthResponse {
        let result: AuthResponse = try await post("/api/v1/auth/apple", json: [
            "identity_token": identityToken,
            "language": language,
            "timezone": timezone as Any,
        ], auth: false)
        store(result)
        return result
    }

    func signInWithGoogle(idToken: String, language: String = "ru",
                          timezone: String? = TimeZone.current.identifier) async throws -> AuthResponse {
        let result: AuthResponse = try await post("/api/v1/auth/google", json: [
            "id_token": idToken,
            "language": language,
            "timezone": timezone as Any,
        ], auth: false)
        store(result)
        return result
    }

    private func store(_ auth: AuthResponse) {
        token = auth.accessToken
        userId = auth.userId
    }

    func me() async throws -> MeResponse {
        try await get("/api/v1/auth/me")
    }

    func redeemLinkCode(_ code: String) async throws -> LinkResult {
        try await post("/api/v1/auth/link", json: ["code": code])
    }

    // MARK: - Каталог и интейк
    //
    // Внимание: язык передаётся ДВУМЯ способами. Каталожные эндпоинты (`/modules`,
    // `/intake`) и аудио берут его из query `?lang=`; все остальные игнорируют query
    // и читают `User.preferred_language`. Поэтому язык надо и передавать, и сохранять.

    func modules(lang: String = "ru") async throws -> [ModuleSummary] {
        try await get("/api/v1/modules?lang=\(lang)")
    }

    func intake(lang: String = "ru") async throws -> IntakeResponse {
        try await get("/api/v1/intake?lang=\(lang)")
    }

    func submitIntake(answers: [Int: Int]) async throws -> IntakeResult {
        // ключи ответов — СТРОКИ ("1"…"30"), значения 0..4.
        // Пропущенные вопросы бэкенд молча считает нулями, а значение вне 0..4 даёт
        // HTTP 500 — поэтому валидируем здесь, а не надеемся на сервер.
        var payload: [String: Int] = [:]
        for (n, v) in answers {
            payload[String(n)] = min(max(v, 0), 4)
        }
        return try await post("/api/v1/intake/submit", json: ["answers": payload])
    }

    // MARK: - Программы

    func enrollments() async throws -> [EnrollmentSummary] {
        struct Wrapper: Codable { let enrollments: [EnrollmentSummary] }
        let w: Wrapper = try await post("/api/v1/users/enrollments", json: [:])
        return w.enrollments
    }

    func enroll(moduleCode: String) async throws -> EnrollResponse {
        try await post("/api/v1/enroll", json: ["module_code": moduleCode])
    }

    func abandonActive() async throws {
        let _: EmptyResponse = try await post("/api/v1/users/abandon-active", json: [:])
    }

    func enrollmentStatus(eid: Int) async throws -> EnrollmentStatusResponse {
        try await get("/api/v1/enrollments/\(eid)/status")
    }

    // MARK: - День

    func daySteps(eid: Int) async throws -> DayResponse {
        try await get("/api/v1/enrollments/\(eid)/day-steps")
    }

    func openDay(eid: Int) async throws -> OpenDayResponse {
        try await post("/api/v1/enrollments/\(eid)/open-day", json: [:])
    }

    func closeDay(eid: Int, taskStatus: TaskStatus?, taskAnswer: String?,
                  quizAnswer: String?, reflection: [String]) async throws -> CloseDayResponse {
        try await post("/api/v1/enrollments/\(eid)/close-day", json: [
            "task_status": taskStatus?.rawValue as Any,
            "task_answer": taskAnswer as Any,
            "quiz_answer": quizAnswer as Any,
            "reflection": reflection,
        ])
    }

    // MARK: - Самопроверка

    func selfcheckQuestions(eid: Int) async throws -> SelfcheckQuestions {
        try await get("/api/v1/enrollments/\(eid)/selfcheck-questions")
    }

    func submitSelfcheck(eid: Int, answers: [Int: Int],
                         morning: [Int: Int], evening: [Int: Int]) async throws -> SelfcheckResult {
        // значения — ИНДЕКСЫ вариантов (0-based), не тексты
        func stringKeyed(_ d: [Int: Int]) -> [String: Int] {
            Dictionary(uniqueKeysWithValues: d.map { (String($0.key), $0.value) })
        }
        return try await post("/api/v1/enrollments/\(eid)/selfcheck", json: [
            "answers": stringKeyed(answers),
            "morning": stringKeyed(morning),
            "evening": stringKeyed(evening),
        ])
    }

    // MARK: - Путь

    func weekInsight(eid: Int) async throws -> InsightResponse {
        try await post("/api/v1/enrollments/\(eid)/week-insight", json: [:])
    }

    func programInsight(eid: Int) async throws -> InsightResponse {
        try await post("/api/v1/enrollments/\(eid)/insight", json: [:])
    }

    func finalProducts() async throws -> [FinalProductItem] {
        struct Wrapper: Codable { let items: [FinalProductItem] }
        let w: Wrapper = try await post("/api/v1/final-products/list", json: [:])
        return w.items
    }

    // MARK: - Дневник

    func journal(moduleCode: String? = nil) async throws -> [JournalEntry] {
        var body: [String: Any] = [:]
        if let moduleCode { body["module_code"] = moduleCode }
        let list: JournalList = try await post("/api/v1/journal/list", json: body)
        return list.entries
    }

    func addNote(_ text: String, moduleCode: String? = nil) async throws {
        var body: [String: Any] = ["text": text]
        if let moduleCode { body["module_code"] = moduleCode }
        let _: EmptyResponse = try await post("/api/v1/journal", json: body)
    }

    // MARK: - Прочее

    func askAI(question: String, context: String?) async throws -> AskAIResponse {
        try await post("/api/v1/ai/ask", json: [
            "question": question,
            "context": context as Any,
        ])
    }

    func resolveAudio(code: String, lang: String = "ru") async throws -> AudioResolve {
        try await get("/api/v1/audio/\(code)/resolve?lang=\(lang)")
    }

    /// Прямая ссылка на файл — используется, когда `resolve.url == nil`
    /// (публичный базовый URL для аудио ещё не настроен на бэкенде).
    nonisolated func audioFileURL(code: String, lang: String = "ru") -> URL? {
        URL(string: "\(baseURL)/api/v1/audio/\(code)/file?lang=\(lang)")
    }

    func updateSettings(slot: String?, hour: Int?, minute: Int?,
                        timezone: String?, language: String?) async throws {
        // бэкенд принимает ОДИН слот за вызов
        var body: [String: Any] = [:]
        if let slot { body["slot"] = slot }
        if let hour { body["hour"] = hour }
        if let minute { body["minute"] = minute }
        if let timezone { body["timezone"] = timezone }
        if let language { body["language"] = language }
        let _: EmptyResponse = try await post("/api/v1/users/settings/update", json: body)
    }

    func registerDevice(token deviceToken: String, sandbox: Bool, language: String?) async throws {
        let _: EmptyResponse = try await post("/api/v1/devices/register", json: [
            "token": deviceToken,
            "sandbox": sandbox,
            "language": language as Any,
        ])
    }

    func unregisterDevice(token deviceToken: String) async throws {
        let _: EmptyResponse = try await post("/api/v1/devices/unregister",
                                              json: ["token": deviceToken])
    }

    // MARK: - Ядро HTTP

    private func get<T: Decodable>(_ path: String) async throws -> T {
        try await execute(makeRequest(path, method: "GET"))
    }

    private func post<T: Decodable>(_ path: String, json: [String: Any],
                                    auth: Bool = true) async throws -> T {
        var req = try makeRequest(path, method: "POST", auth: auth)
        // NSNull вместо nil: JSONSerialization не принимает Optional.none
        let cleaned = json.compactMapValues { value -> Any? in
            if value is NSNull { return nil }
            if case Optional<Any>.none = value { return nil }
            return value
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: cleaned)
        return try await execute(req)
    }

    private func makeRequest(_ path: String, method: String, auth: Bool = true) throws -> URLRequest {
        let normalizedPath = path.hasPrefix("/") ? path : "/\(path)"
        guard let url = URL(string: baseURL + normalizedPath) else {
            throw APIError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if auth, let token {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            // сеть отделена от авторизации: офлайн не должен выглядеть как разлогин
            switch error.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed:
                throw APIError.offline
            case .timedOut:
                throw APIError.timedOut
            case .cancelled:
                throw CancellationError()
            default:
                throw APIError.offline
            }
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(status: -1, message: L10n("error.badResponse").text)
        }
        guard (200...299).contains(http.statusCode) else {
            throw apiError(data: data, status: http.statusCode, path: request.url?.path ?? "")
        }
        // пустое тело у эндпоинтов без содержательного ответа
        if data.isEmpty, let empty = EmptyResponse() as? T { return empty }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    /// Разбор тела ошибки FastAPI: три формы `detail` — строка, объект с `message`, отсутствие.
    private func apiError(data: Data, status: Int, path: String) -> APIError {
        var message = ""
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = object["detail"] {
            if let s = detail as? String {
                message = s
            } else if let nested = detail as? [String: Any],
                      let m = nested["message"] as? String {
                message = m
            } else if let arr = detail as? [[String: Any]],
                      let m = arr.first?["msg"] as? String {
                message = m                       // форма валидации Pydantic
            }
        }

        switch status {
        case 401:
            return .unauthorized(message)
        case 403:
            return .forbidden(message)
        case 404:
            return .notFound
        case 409:
            return .invalidState(message)
        case 500:
            // На этих путях 500 означает «неверное состояние»: у бэкенда нет
            // обработчиков исключений, ValueError в сервисах становится 500, а не 422.
            let stateful = ["open-day", "close-day", "complete-day", "selfcheck"]
            if stateful.contains(where: path.contains) {
                return .invalidState(message)
            }
            return .server(status: status, message: message.isEmpty
                           ? L10n("error.server").text : message)
        default:
            return .server(status: status, message: message.isEmpty
                           ? "HTTP \(status)" : message)
        }
    }
}

/// Для эндпоинтов, чей ответ нам не нужен.
struct EmptyResponse: Codable, Sendable {
    init() {}
    init(from decoder: Decoder) throws {}
}
