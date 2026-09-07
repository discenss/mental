import SwiftUI

/// Вкладка «Пройденный путь» — новая, в Rhythmos её нет.
///
/// Собирается из существующих эндпоинтов Mental: `status` (зоны недель, прогресс),
/// `week-insight` и `insight` (ИИ-разборы, для которых в Rhythmos был только клиент,
/// но не экран) и `final-products/list` (личные итоги).
struct PathView: View {
    let goToToday: () -> Void

    @StateObject private var vm = PathViewModel()
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.xl) {
                    if let error = vm.error {
                        ErrorBanner(error: error) { Task { await vm.load() } }
                    }

                    if vm.isLoading && vm.status == nil {
                        ProgressView().tint(t.terracotta)
                            .frame(maxWidth: .infinity, minHeight: 200)
                    } else if let status = vm.status {
                        progressSection(status)
                        weeksSection(status)
                        insightsSection
                        achievementsSection
                    } else {
                        EmptyStateCard(icon: "map",
                                       title: "path.empty",
                                       message: "path.emptyBody",
                                       actionTitle: "today.chooseRoute",
                                       action: goToToday)
                    }
                }
                .padding(t.spacing.xl)
            }
            .refreshable { await vm.load() }
        }
        .navigationTitle(Text("path.title"))
        .task { await vm.load() }
    }

    // MARK: - Прогресс

    private func progressSection(_ status: EnrollmentStatusResponse) -> some View {
        PageCard {
            Text(status.name)
                .font(t.font.displaySerif(20))
                .foregroundStyle(t.ink)

            // total_weeks/total_days/days_total захардкожены в бэкенде (6/7/42) —
            // берём оттуда, а не считаем сами
            HStack(alignment: .firstTextBaseline, spacing: t.spacing.xs) {
                Text("\(status.daysCompleted)")
                    .font(t.font.numericL)
                    .foregroundStyle(t.terracotta)
                Text("path.progress \(status.daysCompleted) \(status.daysTotal)")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkMuted)
            }
            .accessibilityElement(children: .combine)

            ProgressView(value: Double(status.daysCompleted),
                         total: Double(max(status.daysTotal, 1)))
                .tint(t.terracotta)

            if status.status == .active || status.status == .selfcheckDue {
                Text("today.weekDay \(status.week) \(status.day)")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkDim)
            }
        }
    }

    // MARK: - Зоны недель

    private func weeksSection(_ status: EnrollmentStatusResponse) -> some View {
        VStack(alignment: .leading, spacing: t.spacing.m) {
            LabelTag(text: L10n("path.weeks").text, color: t.inkMuted)

            // Визуальная шкала пройденного: по одной ячейке на неделю.
            // Баллов нет — только зона, как и задумано (§16).
            HStack(spacing: t.spacing.s) {
                ForEach(1...max(status.totalWeeks, 1), id: \.self) { week in
                    let zone = status.weeks.first { $0.week == week }?.zone
                    VStack(spacing: t.spacing.xs) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(zone.map { t.zoneColor($0) } ?? t.inkWhisper.opacity(0.4))
                            .frame(height: 40)
                        Text("\(week)")
                            .font(t.font.labelS)
                            .foregroundStyle(t.inkDim)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(Text("path.week \(week)"))
                    .accessibilityValue(zone.map { Text(L10n($0.titleKey)) }
                                        ?? Text("a11y.notSelected"))
                }
            }
        }
    }

    // MARK: - ИИ-разборы

    private var insightsSection: some View {
        VStack(alignment: .leading, spacing: t.spacing.m) {
            InsightCard(title: "path.weekInsight",
                        icon: "chart.bar.doc.horizontal",
                        accent: t.dustyBlue,
                        state: vm.weekInsight) {
                Task { await vm.loadWeekInsight() }
            }

            if vm.status?.status == .completed {
                InsightCard(title: "path.programInsight",
                            icon: "sparkles.rectangle.stack",
                            accent: t.terracotta,
                            state: vm.programInsight) {
                    Task { await vm.loadProgramInsight() }
                }
            }
        }
    }

    // MARK: - Личные итоги

    @ViewBuilder
    private var achievementsSection: some View {
        if !vm.finalProducts.isEmpty {
            VStack(alignment: .leading, spacing: t.spacing.m) {
                LabelTag(text: L10n("path.achievements").text, color: t.amber)
                ForEach(vm.finalProducts) { product in
                    NavigationLink {
                        FinalProductView(product: product)
                    } label: {
                        PageCard {
                            HStack(spacing: t.spacing.m) {
                                Image(systemName: "doc.text")
                                    .font(.system(size: 18))
                                    .foregroundStyle(t.amber)
                                    .accessibilityHidden(true)
                                Text(product.moduleName ?? product.module ?? "")
                                    .font(t.font.bodyEmphasized)
                                    .foregroundStyle(t.ink)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12))
                                    .foregroundStyle(t.inkDim)
                                    .accessibilityHidden(true)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

// MARK: - Карточка разбора

enum InsightState {
    case idle
    case loading
    case ready(String)
    case disabled
}

struct InsightCard: View {
    let title: L10n
    let icon: String
    let accent: Color
    let state: InsightState
    let onLoad: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        PageCard {
            HStack(spacing: t.spacing.s) {
                Image(systemName: icon)
                    .font(.system(size: 13))
                    .foregroundStyle(accent)
                    .accessibilityHidden(true)
                LabelTag(text: title.text, color: accent)
            }

            switch state {
            case .idle:
                GhostButton(title: "path.insightLoad", icon: "sparkles", action: onLoad)
            case .loading:
                HStack(spacing: t.spacing.s) {
                    ProgressView().tint(accent)
                    Text("common.loading")
                        .font(t.font.caption)
                        .foregroundStyle(t.inkDim)
                }
            case .ready(let text):
                Text(text)
                    .font(t.font.body)
                    .foregroundStyle(t.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            case .disabled:
                Text("path.insightDisabled")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkDim)
            }
        }
    }
}

/// Финальный продукт: массив многострочных строк, где ПЕРВАЯ строка — заголовок,
/// остальное — подсказка. Разделяем по первому переводу строки.
struct FinalProductView: View {
    let product: FinalProductItem

    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.l) {
                    ForEach(Array(product.sections.enumerated()), id: \.offset) { index, section in
                        let parts = section.split(separator: "\n", maxSplits: 1,
                                                  omittingEmptySubsequences: false)
                        let heading = parts.first.map(String.init) ?? ""
                        let body = parts.count > 1 ? String(parts[1]) : nil

                        ContentCard(label: "\(index + 1)",
                                    title: heading,
                                    text: body,
                                    accent: t.amber)
                            .staggerIn(index: min(index, 8))
                    }
                }
                .padding(t.spacing.xl)
            }
        }
        .navigationTitle(Text(product.moduleName ?? "path.achievements"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - ViewModel

@MainActor
final class PathViewModel: ObservableObject {
    @Published private(set) var status: EnrollmentStatusResponse?
    @Published private(set) var finalProducts: [FinalProductItem] = []
    @Published private(set) var weekInsight: InsightState = .idle
    @Published private(set) var programInsight: InsightState = .idle
    @Published private(set) var isLoading = false
    @Published var error: APIError?

    private let api: RidgeAPIProtocol
    private var eid: Int?

    init(api: RidgeAPIProtocol = RidgeAPI.shared) {
        self.api = api
    }

    func load() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let enrollments = try await api.enrollments()
            // показываем активный маршрут; если активного нет — последний завершённый
            let target = enrollments.first { $0.status == .active || $0.status == .selfcheckDue }
                ?? enrollments.first { $0.status == .completed }
            guard let target else {
                status = nil
                return
            }
            eid = target.enrollmentId
            status = try await api.enrollmentStatus(eid: target.enrollmentId)
            finalProducts = (try? await api.finalProducts()) ?? []
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }

    /// `enabled: false` приходит, когда на бэкенде не настроен ключ LLM.
    private static func state(from response: InsightResponse) -> InsightState {
        guard response.enabled, let text = response.text, !text.isEmpty else {
            return .disabled
        }
        return .ready(text)
    }

    /// Разборы грузим по требованию: это обращение к сильной модели, не для каждого входа.
    func loadWeekInsight() async {
        guard let eid else { return }
        weekInsight = .loading
        do {
            let response = try await api.weekInsight(eid: eid)
            weekInsight = Self.state(from: response)
        } catch {
            weekInsight = .disabled
        }
    }

    func loadProgramInsight() async {
        guard let eid else { return }
        programInsight = .loading
        do {
            let response = try await api.programInsight(eid: eid)
            programInsight = Self.state(from: response)
        } catch {
            programInsight = .disabled
        }
    }
}

#Preview {
    NavigationStack { PathView {} }
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
