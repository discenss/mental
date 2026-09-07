import SwiftUI

/// Вкладка «История» — дневник.
///
/// Композиция с `HistoryView` Rhythmos: месячный календарь как навигатор/фильтр,
/// под ним лента карточек. Два разных пустых состояния: «истории ещё нет» (с CTA
/// на «Сегодня») и «в этот день записей нет» (тихая карточка).
struct HistoryView: View {
    let goToToday: () -> Void

    @StateObject private var vm = HistoryViewModel()
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.l) {
                    if let error = vm.error {
                        ErrorBanner(error: error) { Task { await vm.load() } }
                            .padding(.horizontal, t.spacing.xl)
                    }

                    MonthCalendarStrip(
                        month: vm.visibleMonth,
                        selected: vm.selectedDate,
                        markedDays: vm.daysWithEntries,
                        onSelect: { vm.select($0) },
                        onShiftMonth: { vm.shiftMonth(by: $0) })
                        .padding(.horizontal, t.spacing.xl)

                    content
                        .padding(.horizontal, t.spacing.xl)
                }
                .padding(.vertical, t.spacing.l)
            }
            .refreshable { await vm.load() }
        }
        .navigationTitle(Text("history.title"))
        .task { await vm.load() }
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.entries.isEmpty {
            ProgressView().tint(t.terracotta).frame(maxWidth: .infinity, minHeight: 160)
        } else if vm.entries.isEmpty {
            // первое пустое состояние: истории ещё нет вообще
            EmptyStateCard(icon: "book.closed",
                           title: "history.empty",
                           message: "history.emptyBody",
                           actionTitle: "history.goToday",
                           action: goToToday)
        } else {
            let visible = vm.visibleEntries
            if visible.isEmpty {
                // второе пустое состояние: день выбран, но записей в нём нет
                PageCard {
                    HStack(spacing: t.spacing.m) {
                        Image(systemName: "calendar.badge.exclamationmark")
                            .font(.system(size: 20))
                            .foregroundStyle(t.inkWhisper)
                            .accessibilityHidden(true)
                        Text("history.emptyDay")
                            .font(t.font.body)
                            .foregroundStyle(t.inkMuted)
                    }
                }
                Button {
                    vm.select(nil)
                } label: {
                    Text("history.allEntries")
                        .font(t.font.caption)
                        .foregroundStyle(t.terracotta)
                }
            } else {
                LazyVStack(spacing: t.spacing.m) {
                    ForEach(Array(visible.enumerated()), id: \.element.id) { index, entry in
                        NavigationLink {
                            JournalEntryDetailView(entry: entry)
                        } label: {
                            JournalEntryCard(entry: entry)
                        }
                        .buttonStyle(.plain)
                        .staggerIn(index: min(index, 8))
                    }
                }
            }
        }
    }
}

// MARK: - Календарь

/// Месячная сетка 7×N, недели с понедельника. Кружок 28×28 на день; выбранный залит
/// терракотой, дни с записями помечены точкой.
struct MonthCalendarStrip: View {
    let month: Date
    let selected: Date?
    let markedDays: Set<Date>
    let onSelect: (Date?) -> Void
    let onShiftMonth: (Int) -> Void

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    private var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.firstWeekday = 2                          // понедельник
        c.locale = language.current.locale
        return c
    }

    var body: some View {
        VStack(spacing: t.spacing.m) {
            HStack {
                Button { onShiftMonth(-1) } label: {
                    Image(systemName: "chevron.left").font(.system(size: 13, weight: .medium))
                }
                .accessibilityLabel(Text("common.back"))

                Spacer()
                Text(DateFormatting.monthTitle(month, language: language.current))
                    .font(t.font.bodyEmphasized)
                    .foregroundStyle(t.ink)
                Spacer()

                Button { onShiftMonth(1) } label: {
                    Image(systemName: "chevron.right").font(.system(size: 13, weight: .medium))
                }
                .accessibilityLabel(Text("common.next"))
            }
            .foregroundStyle(t.inkMuted)

            HStack(spacing: 0) {
                ForEach(DateFormatting.weekdaySymbols(language: language.current), id: \.self) { day in
                    Text(day)
                        .font(t.font.labelS)
                        .foregroundStyle(t.inkDim)
                        .frame(maxWidth: .infinity)
                }
            }

            ForEach(weeks, id: \.first) { week in
                HStack(spacing: 0) {
                    ForEach(week, id: \.self) { date in
                        dayCell(date)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .padding(t.spacing.l)
        .background(t.surface)
        .clipShape(RoundedRectangle(cornerRadius: t.corners.cardLarge))
        .overlay(
            RoundedRectangle(cornerRadius: t.corners.cardLarge)
                .strokeBorder(t.border, lineWidth: 0.5)
        )
    }

    @ViewBuilder
    private func dayCell(_ date: Date) -> some View {
        let inMonth = calendar.isDate(date, equalTo: month, toGranularity: .month)
        let isSelected = selected.map { calendar.isDate($0, inSameDayAs: date) } ?? false
        let hasEntries = markedDays.contains { calendar.isDate($0, inSameDayAs: date) }
        let isToday = calendar.isDateInToday(date)

        Button {
            Haptics.selection()
            onSelect(isSelected ? nil : date)
        } label: {
            VStack(spacing: 3) {
                Text("\(calendar.component(.day, from: date))")
                    .font(t.font.caption)
                    .foregroundStyle(isSelected ? .white
                                     : (inMonth ? t.ink : t.inkWhisper))
                    .frame(width: 28, height: 28)
                    .background(isSelected ? t.terracotta : .clear)
                    .clipShape(Circle())
                    .overlay(
                        Circle().strokeBorder(
                            isToday && !isSelected ? t.terracotta.opacity(0.5) : .clear,
                            lineWidth: 1)
                    )
                Circle()
                    .fill(hasEntries ? t.sage : .clear)
                    .frame(width: 4, height: 4)
            }
        }
        .disabled(!inMonth)
        .accessibilityLabel(Text(DateFormatting.dayTitle(date, language: language.current)))
        .accessibilityValue(Text(isSelected ? "a11y.selected" : "a11y.notSelected"))
    }

    /// Сетка недель, покрывающая месяц целиком (с добором дней соседних месяцев).
    private var weeks: [[Date]] {
        guard
            let monthInterval = calendar.dateInterval(of: .month, for: month),
            let firstWeek = calendar.dateInterval(of: .weekOfMonth, for: monthInterval.start)
        else { return [] }

        var result: [[Date]] = []
        var cursor = firstWeek.start
        while cursor < monthInterval.end {
            var week: [Date] = []
            for offset in 0..<7 {
                if let day = calendar.date(byAdding: .day, value: offset, to: cursor) {
                    week.append(day)
                }
            }
            result.append(week)
            guard let nextWeek = calendar.date(byAdding: .weekOfYear, value: 1, to: cursor)
            else { break }
            cursor = nextWeek
        }
        return result
    }
}

// MARK: - Карточки записей

struct JournalEntryCard: View {
    let entry: JournalEntry

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    private var accent: Color {
        switch entry.sourceType {
        case .task:         return t.sage
        case .reflection:   return t.terracotta
        case .finalProduct: return t.amber
        case .note, .unknown: return t.dustyBlue
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: t.spacing.m) {
            RoundedRectangle(cornerRadius: 1.5)
                .fill(accent)
                .frame(width: 3)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: t.spacing.xs) {
                HStack(spacing: t.spacing.s) {
                    Image(systemName: entry.sourceType.symbol)
                        .font(.system(size: 11))
                        .foregroundStyle(accent)
                        .accessibilityHidden(true)
                    LabelTag(text: L10n(entry.sourceType.titleKey).text,
                             color: accent)
                    Spacer(minLength: 0)
                    if let date = DateParsing.date(from: entry.createdAt) {
                        Text(DateFormatting.time(date, language: language.current))
                            .font(t.font.labelS)
                            .foregroundStyle(t.inkDim)
                    }
                }

                // у заметок и финального продукта week/day = null
                if let week = entry.week, let day = entry.day {
                    Text("today.weekDay \(week) \(day)")
                        .font(t.font.labelS)
                        .foregroundStyle(t.inkDim)
                }

                Text(entry.text)
                    .font(t.font.body)
                    .foregroundStyle(t.ink)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(t.spacing.l)
        .background(t.surface)
        .clipShape(RoundedRectangle(cornerRadius: t.corners.card))
        .overlay(
            RoundedRectangle(cornerRadius: t.corners.card)
                .strokeBorder(t.border, lineWidth: 0.5)
        )
        .accessibilityElement(children: .combine)
    }
}

struct JournalEntryDetailView: View {
    let entry: JournalEntry

    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.l) {
                    if let date = DateParsing.date(from: entry.createdAt) {
                        Text(DateFormatting.dayTitle(date, language: language.current))
                            .font(t.font.displaySerif(20))
                            .foregroundStyle(t.ink)
                    }
                    if let name = entry.moduleName {
                        PillBadge(text: name)
                    }
                    Text(entry.text)
                        .font(t.font.body)
                        .foregroundStyle(t.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(t.spacing.xl)
            }
        }
        .navigationTitle(Text(L10n(entry.sourceType.titleKey)))
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - ViewModel

@MainActor
final class HistoryViewModel: ObservableObject {
    @Published private(set) var entries: [JournalEntry] = []
    @Published private(set) var visibleMonth = Date()
    @Published private(set) var selectedDate: Date?
    @Published private(set) var isLoading = false
    @Published var error: APIError?

    private let api: RidgeAPIProtocol
    private var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.firstWeekday = 2
        return c
    }

    init(api: RidgeAPIProtocol = RidgeAPI.shared) {
        self.api = api
    }

    /// Даты, в которые есть записи — для точек в календаре.
    var daysWithEntries: Set<Date> {
        Set(entries.compactMap { DateParsing.date(from: $0.createdAt) }
            .map { calendar.startOfDay(for: $0) })
    }

    /// Записи выбранного дня, либо все (записи приходят отсортированными по created_at DESC).
    var visibleEntries: [JournalEntry] {
        guard let selectedDate else { return entries }
        return entries.filter { entry in
            guard let date = DateParsing.date(from: entry.createdAt) else { return false }
            return calendar.isDate(date, inSameDayAs: selectedDate)
        }
    }

    func load() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            entries = try await api.journal(moduleCode: nil)
        } catch let e as APIError {
            error = e
        } catch {
            self.error = .server(status: 0, message: error.localizedDescription)
        }
    }

    func select(_ date: Date?) {
        selectedDate = date.map { calendar.startOfDay(for: $0) }
    }

    func shiftMonth(by delta: Int) {
        if let next = calendar.date(byAdding: .month, value: delta, to: visibleMonth) {
            visibleMonth = next
        }
    }
}

#Preview {
    NavigationStack { HistoryView {} }
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
