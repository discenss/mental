import SwiftUI

/// Недельная самопроверка (день 7).
///
/// Порядок: **блок маркеров** (5 «утренних» + 5 «вечерних») → 10 вопросов итогов недели
/// → зона с текстом и рекомендацией. Маркеры спрашиваются РАЗ В НЕДЕЛЮ именно здесь,
/// а не каждый день: ежедневные 10 вопросов утомляли и не давали новой информации
/// (коммит 9990668). Деление morning/evening — контентное, это два разных набора
/// вопросов, а не время суток.
///
/// Слово «диагностика» в интерфейсе запрещено (§16) — только «самопроверка».
/// Баллы пользователю не показываются.
struct SelfcheckView: View {
    let eid: Int
    let onFinish: () -> Void

    @StateObject private var vm: SelfcheckViewModel
    @Environment(\.theme) private var t
    @Environment(\.dismiss) private var dismiss

    init(eid: Int, onFinish: @escaping () -> Void) {
        self.eid = eid
        self.onFinish = onFinish
        _vm = StateObject(wrappedValue: SelfcheckViewModel(eid: eid))
    }

    var body: some View {
        NavigationStack {
            ZStack {
                t.paper.ignoresSafeArea()

                if let result = vm.result {
                    resultScreen(result)
                } else {
                    questionnaire
                }
            }
            .navigationTitle(Text(vm.result == nil ? "selfcheck.title" : "selfcheck.resultTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if vm.result == nil {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("common.cancel") { dismiss() }
                    }
                }
            }
        }
        .task { await vm.load() }
        .interactiveDismissDisabled(vm.result != nil)
    }

    // MARK: - Опросник

    private var questionnaire: some View {
        VStack(spacing: 0) {
            ProgressDashes(total: max(vm.totalPages, 1), current: vm.page + 1)
                .padding(.horizontal, t.spacing.xl)
                .padding(.top, t.spacing.m)

            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.xl) {
                    if let error = vm.error {
                        ErrorBanner(error: error) { Task { await vm.load() } }
                    }

                    if vm.isLoading && vm.questions == nil {
                        ProgressView().tint(t.terracotta).frame(maxWidth: .infinity, minHeight: 200)
                    } else {
                        pageContent
                    }
                }
                .padding(t.spacing.xl)
            }

            bottomBar
        }
    }

    @ViewBuilder
    private var pageContent: some View {
        switch vm.currentPage {
        case .markersIntro:
            VStack(alignment: .leading, spacing: t.spacing.m) {
                Text("selfcheck.markersIntro")
                    .font(t.font.titleS)
                    .foregroundStyle(t.ink)
                    .fixedSize(horizontal: false, vertical: true)
                InlineSerifQuote(text: L10n("selfcheck.markersMorning").text)
            }

        case .marker(let phase, let index):
            if let marker = vm.marker(phase: phase, index: index) {
                markerBlock(marker, phase: phase)
            }

        case .question(let index):
            if let question = vm.question(at: index) {
                questionBlock(question)
            }

        case .none:
            EmptyView()
        }
    }

    private func markerBlock(_ marker: Marker, phase: MarkerPhase) -> some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            LabelTag(text: L10n(phase == .morning
                          ? "selfcheck.markersMorning"
                          : "selfcheck.markersEvening").text,
                     color: phase == .morning ? t.amber : t.dustyBlue)

            Text(marker.question)
                .font(t.font.titleS)
                .foregroundStyle(t.ink)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: t.spacing.s) {
                ForEach(Array(marker.options.enumerated()), id: \.offset) { index, option in
                    ChoiceCard(text: option,
                               isSelected: vm.markerAnswer(phase: phase, idx: marker.idx) == index) {
                        vm.setMarker(phase: phase, idx: marker.idx, choice: index)
                    }
                }
            }
        }
    }

    private func questionBlock(_ question: SelfcheckQuestion) -> some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            LabelTag(text: L10n("selfcheck.questions").text, color: t.terracotta)

            Text(question.question)
                .font(t.font.titleS)
                .foregroundStyle(t.ink)
                .fixedSize(horizontal: false, vertical: true)

            // Индексы вариантов, а не тексты — так их ждёт бэкенд
            VStack(spacing: t.spacing.s) {
                ForEach(Array(question.options.enumerated()), id: \.offset) { index, option in
                    ChoiceCard(text: option, isSelected: vm.answers[question.q] == index) {
                        vm.answers[question.q] = index
                    }
                }
            }
        }
    }

    private var bottomBar: some View {
        HStack(spacing: t.spacing.m) {
            if vm.page > 0 {
                GhostButton(title: "common.back", icon: "chevron.left") { vm.previous() }
                    .frame(maxWidth: 140)
            }
            AccentButton(title: vm.isLastPage ? "selfcheck.submit" : "common.next",
                         isLoading: vm.isSubmitting,
                         isDisabled: !vm.canAdvance) {
                if vm.isLastPage {
                    Task { await vm.submit() }
                } else {
                    vm.next()
                }
            }
        }
        .padding(.horizontal, t.spacing.xl)
        .padding(.vertical, t.spacing.l)
        .background(t.paper)
        .overlay(alignment: .top) { Divider().foregroundStyle(t.border) }
    }

    // MARK: - Результат

    private func resultScreen(_ result: SelfcheckResult) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: t.spacing.xl) {
                HStack(spacing: t.spacing.m) {
                    Circle()
                        .fill(t.zoneColor(result.zone))
                        .frame(width: 14, height: 14)
                        .accessibilityHidden(true)
                    Text(L10n(result.zone.titleKey))
                        .font(t.font.titleM)
                        .foregroundStyle(t.ink)
                }

                if let text = result.userText {
                    PageCard {
                        Text(text)
                            .font(t.font.body)
                            .foregroundStyle(t.inkMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                // Мягкие тематические блоки по критичным ответам.
                // Не диагноз, без слов «критично» и «красный флаг» (§11.3).
                ForEach(Array(result.criticals.enumerated()), id: \.offset) { index, block in
                    ContentCard(label: L10n("selfcheck.recommendation").text,
                                title: nil,
                                text: block,
                                accent: t.dustyBlue,
                                icon: "lightbulb")
                        .staggerIn(index: index)
                }

                if let recommendation = result.recommendation {
                    ContentCard(label: L10n("selfcheck.recommendation").text,
                                title: nil,
                                text: recommendation,
                                accent: t.sage,
                                icon: "arrow.forward.circle")
                }

                AccentButton(title: "selfcheck.continueNext") {
                    onFinish()
                    dismiss()
                }
            }
            .padding(t.spacing.xl)
        }
    }
}

enum MarkerPhase {
    case morning
    case evening
}

/// Страница опросника: сначала блок маркеров, затем 10 вопросов — по одному на экран.
enum SelfcheckPage: Equatable {
    case markersIntro
    case marker(MarkerPhase, Int)
    case question(Int)
    case none
}

extension MarkerPhase: Equatable {}

@MainActor
final class SelfcheckViewModel: ObservableObject {
    @Published private(set) var questions: SelfcheckQuestions?
    @Published private(set) var result: SelfcheckResult?
    @Published var answers: [Int: Int] = [:]
    @Published private(set) var morning: [Int: Int] = [:]
    @Published private(set) var evening: [Int: Int] = [:]
    @Published var page = 0
    @Published private(set) var isLoading = false
    @Published private(set) var isSubmitting = false
    @Published var error: APIError?

    private let eid: Int
    private let api: RidgeAPIProtocol

    init(eid: Int, api: RidgeAPIProtocol = RidgeAPI.shared) {
        self.eid = eid
        self.api = api
    }

    /// 1 вступление + маркеры + вопросы.
    var totalPages: Int {
        guard let q = questions else { return 1 }
        return 1 + q.morningMarkers.count + q.eveningMarkers.count + q.questions.count
    }

    var isLastPage: Bool { page >= totalPages - 1 }

    var currentPage: SelfcheckPage {
        guard let q = questions else { return .none }
        if page == 0 { return .markersIntro }
        var cursor = page - 1
        if cursor < q.morningMarkers.count { return .marker(.morning, cursor) }
        cursor -= q.morningMarkers.count
        if cursor < q.eveningMarkers.count { return .marker(.evening, cursor) }
        cursor -= q.eveningMarkers.count
        if cursor < q.questions.count { return .question(cursor) }
        return .none
    }

    /// Маркеры и вопросы самопроверки обязательны: без них зона не считается.
    var canAdvance: Bool {
        switch currentPage {
        case .markersIntro, .none:
            return true
        case .marker(let phase, let index):
            guard let marker = marker(phase: phase, index: index) else { return true }
            return markerAnswer(phase: phase, idx: marker.idx) != nil
        case .question(let index):
            guard let question = question(at: index) else { return true }
            return answers[question.q] != nil
        }
    }

    func marker(phase: MarkerPhase, index: Int) -> Marker? {
        let list = phase == .morning ? questions?.morningMarkers : questions?.eveningMarkers
        guard let list, list.indices.contains(index) else { return nil }
        return list[index]
    }

    func question(at index: Int) -> SelfcheckQuestion? {
        guard let list = questions?.questions, list.indices.contains(index) else { return nil }
        return list[index]
    }

    func markerAnswer(phase: MarkerPhase, idx: Int) -> Int? {
        phase == .morning ? morning[idx] : evening[idx]
    }

    func setMarker(phase: MarkerPhase, idx: Int, choice: Int) {
        if phase == .morning { morning[idx] = choice } else { evening[idx] = choice }
    }

    func next() { if !isLastPage { page += 1 } }
    func previous() { if page > 0 { page -= 1 } }

    func load() async {
        guard questions == nil else { return }
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            questions = try await api.selfcheckQuestions(eid: eid)
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }

    func submit() async {
        guard !isSubmitting else { return }
        isSubmitting = true
        error = nil
        defer { isSubmitting = false }
        do {
            result = try await api.submitSelfcheck(eid: eid, answers: answers,
                                                   morning: morning, evening: evening)
            Haptics.success()
        } catch let e as APIError {
            // 500 на этом пути означает «неверное состояние»: самопроверка доступна
            // только при status == selfcheck_due
            error = e
            Haptics.error()
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }
}

#Preview {
    SelfcheckView(eid: 1) {}
        .environment(\.theme, .warm)
}
