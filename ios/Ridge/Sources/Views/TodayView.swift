import SwiftUI

/// Главный экран: день маршрута.
///
/// Композиция взята с `TodayView` Rhythmos: hero-заголовок 200pt вместо навбара,
/// `ScrollView` с `.refreshable`, FAB'ы снизу-справа. Содержание — из Mental.
///
/// Три состояния по `status`: `active` (утро/вечер), `selfcheck_due`, `completed`.
struct TodayView: View {
    @StateObject private var vm = TodayViewModel()
    @EnvironmentObject private var language: LanguageStore
    @EnvironmentObject private var auth: AuthViewModel
    @Environment(\.theme) private var t

    @State private var showAskAI = false
    @State private var showNote = false
    @State private var showEveningFlow = false
    @State private var showSelfcheck = false
    @State private var showModulePicker = false
    @State private var expandedCard: String?

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            t.paper.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.xl) {
                    HeroHeader(dateLine: DateFormatting.heroDate(Date(), language: language.current),
                               greeting: TimeOfDay.current().greetingKey.text,
                               context: contextLine)

                    VStack(alignment: .leading, spacing: t.spacing.l) {
                        if let error = vm.error {
                            ErrorBanner(error: error) { vm.load() }
                                .onAppear { if error.requiresSignOut { auth.handleUnauthorized() } }
                        }

                        content
                    }
                    .padding(.horizontal, t.spacing.xl)
                    .padding(.bottom, 96)          // место под FAB'ы
                }
            }
            .refreshable { await vm.refresh() }
            .navigationBarHidden(true)             // hero заменяет навбар

            if vm.hasRoute {
                fabStack
            }
        }
        .task {
            vm.load()
            await vm.loadModules(language: language.current.rawValue)
        }
        .onDisappear { vm.cancelLoading() }
        .sheet(isPresented: $showAskAI) { AskAIView(context: aiContext) }
        .sheet(isPresented: $showNote) {
            NoteSheet { text in Task { await vm.addNote(text) } }
        }
        .sheet(isPresented: $showEveningFlow) {
            DayFlowView(vm: vm) { showEveningFlow = false }
        }
        .sheet(isPresented: $showSelfcheck) {
            if let eid = vm.eid {
                SelfcheckView(eid: eid) {
                    showSelfcheck = false
                    vm.load()
                }
            }
        }
        .sheet(isPresented: $showModulePicker) {
            ModulePickerSheet(modules: vm.modules) { code in
                showModulePicker = false
                Task { await vm.enroll(in: code) }
            }
        }
    }

    private var contextLine: String? {
        guard let day = vm.day, day.isActive, let w = day.week, let d = day.day else {
            return vm.enrollment?.name
        }
        return L10n("today.weekDay").format(w, d)
    }

    private var aiContext: String? {
        guard let day = vm.day, day.isActive else { return nil }
        return [day.dayTitle, vm.focusStep?.focus].compactMap { $0 }.joined(separator: "\n")
    }

    // MARK: - Содержимое по состоянию

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.day == nil {
            ProgressView().tint(t.terracotta).frame(maxWidth: .infinity, minHeight: 160)
        } else if !vm.hasRoute {
            EmptyStateCard(icon: "compass.drawing",
                           title: "today.noRoute",
                           message: "today.noRouteBody",
                           actionTitle: "today.chooseRoute") { showModulePicker = true }
        } else if let day = vm.day {
            if day.isCompleted {
                completedState
            } else if day.isSelfcheckDue {
                selfcheckDueState(week: day.week ?? 0)
            } else if vm.isDoneToday {
                doneTodayState
            } else {
                activeDay(day)
            }
        }
    }

    private var completedState: some View {
        EmptyStateCard(icon: "flag.checkered",
                       title: "today.completed",
                       message: "today.completedBody")
    }

    private func selfcheckDueState(week: Int) -> some View {
        // Заголовок содержит номер недели, поэтому собираем строку сами:
        // интерполяция внутрь LocalizedStringKey испортила бы сам ключ.
        let title = L10n("today.selfcheckDue").format(week)
        return PageCard {
            VStack(spacing: t.spacing.m) {
                Image(systemName: "checklist")
                    .font(.system(size: 38, weight: .light))
                    .foregroundStyle(t.inkWhisper)
                    .accessibilityHidden(true)
                Text(title)
                    .font(t.font.titleS)
                    .foregroundStyle(t.ink)
                    .multilineTextAlignment(.center)
                Text("today.selfcheckDueBody")
                    .font(t.font.body)
                    .foregroundStyle(t.inkMuted)
                    .multilineTextAlignment(.center)
                AccentButton(title: "today.selfcheckStart") { showSelfcheck = true }
                    .padding(.top, t.spacing.xs)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, t.spacing.s)
        }
    }

    private var doneTodayState: some View {
        EmptyStateCard(icon: "moon.stars",
                       title: "today.dayDone",
                       message: "today.comeBackTomorrow")
    }

    @ViewBuilder
    private func activeDay(_ day: DayResponse) -> some View {
        if vm.showWeekIntro, let intro = day.weekIntro {
            WeekIntroCard(intro: intro, week: day.week ?? 1)
                .staggerIn(index: 0)
        }

        if let title = day.dayTitle, !title.isEmpty {
            Text(title)
                .font(t.font.displaySerif(20))
                .foregroundStyle(t.ink)
                .staggerIn(index: 1)
        }

        if vm.session == .morning {
            morningContent
        } else {
            eveningPrompt
        }
    }

    /// Утро: вопросы настройки (спец для недели 6) → фокус + задание → аудио.
    @ViewBuilder
    private var morningContent: some View {
        ForEach(Array(vm.intentSteps.enumerated()), id: \.element.id) { index, step in
            if let question = step.question {
                ContentCard(label: L10n("today.intent").text,
                            title: nil,
                            text: question,
                            accent: t.dustyBlue,
                            icon: "sparkle")
                    .staggerIn(index: index + 2)
            }
        }

        if let focus = vm.focusStep {
            ContentCard(label: L10n("today.focus").text,
                        title: nil,
                        text: focus.focus,
                        accent: t.terracotta,
                        icon: "target")
                .staggerIn(index: 3)

            if let task = focus.task {
                ContentCard(label: L10n("today.task").text,
                            title: nil,
                            text: task.text,
                            subtasks: task.subtasks,
                            accent: t.sage,
                            icon: "checkmark.square",
                            isExpanded: expandedCard == "task") {
                    expandedCard = expandedCard == "task" ? nil : "task"
                }
                .staggerIn(index: 4)
            }
        }

        if let audio = vm.audioStep, let code = audio.code {
            AudioCard(code: code, title: audio.title)
                .staggerIn(index: 5)
        }

        AccentButton(title: "today.openDay", isLoading: vm.isSubmitting) {
            Task { await vm.openDay() }
        }
        .padding(.top, t.spacing.s)
        .staggerIn(index: 6)
    }

    /// Вечер: закрыть день — статус задания, квиз, три рефлексии.
    private var eveningPrompt: some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            PageCard {
                HStack(spacing: t.spacing.m) {
                    Image(systemName: "sunset")
                        .font(.system(size: 20))
                        .foregroundStyle(t.terracotta)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("today.dayOpened")
                            .font(t.font.titleS)
                            .foregroundStyle(t.ink)
                        Text("today.dayOpenedBody")
                            .font(t.font.caption)
                            .foregroundStyle(t.inkMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            if let focus = vm.focusStep, let task = focus.task {
                ContentCard(label: L10n("today.task").text,
                            title: nil,
                            text: task.text,
                            subtasks: task.subtasks,
                            accent: t.sage,
                            icon: "checkmark.square")
            }

            AccentButton(title: "today.closeDay") { showEveningFlow = true }
        }
    }

    // MARK: - FAB'ы

    private var fabStack: some View {
        VStack(spacing: t.spacing.m) {
            Button {
                Haptics.light()
                showNote = true
            } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(t.terracotta)
                    .frame(width: 48, height: 48)
                    .background(t.surface)
                    .clipShape(Circle())
                    .overlay(Circle().strokeBorder(t.terracotta.opacity(0.5), lineWidth: 1))
            }
            .accessibilityLabel(Text("today.addNote"))

            Button {
                Haptics.light()
                showAskAI = true
            } label: {
                Image(systemName: "sparkles")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(.white)
                    .frame(width: 56, height: 56)
                    .background(t.terracotta)
                    .clipShape(Circle())
                    .shadow(color: .black.opacity(0.12), radius: 8, y: 4)
            }
            .accessibilityLabel(Text("today.askAI"))
        }
        .padding(.trailing, t.spacing.xl)
        .padding(.bottom, t.spacing.xl)
    }
}

// MARK: - Вводный экран недели

/// Показывается один раз, в день 1. `meaning` сюда НЕ идёт — это методологическое
/// поле для автора контента, не пользовательский текст (см. bot/texts.py::week_intro).
struct WeekIntroCard: View {
    let intro: WeekIntro
    let week: Int

    @Environment(\.theme) private var t

    var body: some View {
        PageCard {
            LabelTag(text: L10n("today.weekIntro").text, color: t.terracotta)

            if let title = intro.title {
                Text(title)
                    .font(t.font.titleS)
                    .foregroundStyle(t.ink)
            }
            if let screen = intro.introScreen {
                Text(screen)
                    .font(t.font.body)
                    .foregroundStyle(t.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let goal = intro.goal {
                labelled("today.weekGoal", goal)
            }
            if let result = intro.result {
                labelled("today.weekResult", result)
            }
            if !intro.keyThemes.isEmpty {
                VStack(alignment: .leading, spacing: t.spacing.xs) {
                    LabelTag(text: L10n("today.keyThemes").text, color: t.inkMuted)
                    ForEach(Array(intro.keyThemes.enumerated()), id: \.offset) { _, theme in
                        Text("• \(theme)")
                            .font(t.font.caption)
                            .foregroundStyle(t.inkMuted)
                    }
                }
            }
        }
    }

    private func labelled(_ key: L10n, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            LabelTag(text: key.text, color: t.sage)
            Text(text)
                .font(t.font.body)
                .foregroundStyle(t.inkMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

#Preview {
    NavigationStack { TodayView() }
        .environmentObject(AuthViewModel())
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
