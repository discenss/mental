import SwiftUI

/// Онбординг: язык → вступление → 30 вопросов → результат → напоминания.
///
/// Механика шагов — из Rhythmos: плоский `step`, `ProgressDashes` сверху, липкая
/// нижняя панель «‹ Назад / Дальше →», и escape-hatch «Выбрать маршрут самому».
/// Право выбора программы остаётся за пользователем — автоперехода нет (§12).
struct OnboardingView: View {
    let onFinish: () -> Void

    @StateObject private var vm = OnboardingViewModel()
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.theme) private var t

    @State private var showModulePicker = false

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()

            VStack(spacing: 0) {
                header

                ScrollView {
                    VStack(alignment: .leading, spacing: t.spacing.xl) {
                        if let error = vm.error {
                            ErrorBanner(error: error) { vm.loadIntake() }
                        }

                        switch vm.step {
                        case .language:  languageStep
                        case .intro:     introStep
                        case .intake:    intakeStep
                        case .result:    resultStep
                        case .reminders: remindersStep
                        }
                    }
                    .padding(t.spacing.xl)
                }

                bottomBar
            }
        }
        .task { vm.loadIntake() }
        .sheet(isPresented: $showModulePicker) {
            ModulePickerSheet(modules: vm.modules) { code in
                Task {
                    showModulePicker = false
                    _ = await vm.enroll(in: code)
                }
            }
        }
    }

    // MARK: - Шапка

    private var header: some View {
        VStack(spacing: t.spacing.m) {
            ProgressDashes(total: OnboardingViewModel.Step.allCases.count,
                           current: vm.step.rawValue + 1)
                .padding(.horizontal, t.spacing.xl)

            if vm.step == .intake, !vm.questions.isEmpty {
                Text("onboarding.intake.progress \(vm.questionIndex + 1) \(vm.questions.count)")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkDim)
            }
        }
        .padding(.top, t.spacing.safeTop)
        .padding(.bottom, t.spacing.m)
    }

    // MARK: - Шаг 0: язык

    private var languageStep: some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            // Заголовок двуязычный — он должен читаться ДО того, как язык выбран
            Text("onboarding.language.title")
                .font(t.font.displaySerif(24))
                .foregroundStyle(t.ink)
            Text("onboarding.language.subtitle")
                .font(t.font.body)
                .foregroundStyle(t.inkMuted)

            VStack(spacing: t.spacing.s) {
                ForEach(AppLanguage.allCases) { lang in
                    ChoiceCard(
                        text: "\(lang.flag)  \(lang.nativeName)",
                        subtitle: lang.isAvailable ? nil : L10n("common.soon").text,
                        isSelected: language.current == lang,
                        isDisabled: !lang.isAvailable
                    ) {
                        language.set(lang)
                        vm.loadIntake()          // тексты приходят на выбранном языке
                    }
                }
            }
        }
    }

    // MARK: - Шаг 1: вступление

    private var introStep: some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            Text("onboarding.intro.title")
                .font(t.font.displaySerif(24))
                .foregroundStyle(t.ink)

            if vm.isLoading && vm.intake == nil {
                ProgressView().tint(t.terracotta)
                    .frame(maxWidth: .infinity)
            } else {
                // client_intro обязателен к показу: снимает тревогу и юридически важен
                // («результат не является диагнозом»). Фолбэк — на случай офлайна.
                PageCard {
                    Text(vm.intake?.clientIntro ?? L10n("onboarding.intro.fallback").text)
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Button {
                showModulePicker = true
            } label: {
                Text("onboarding.skip")
                    .font(t.font.caption)
                    .foregroundStyle(t.inkMuted)
                    .underline()
            }
        }
    }

    // MARK: - Шаг 2: 30 вопросов

    @ViewBuilder
    private var intakeStep: some View {
        if let question = vm.currentQuestion {
            VStack(alignment: .leading, spacing: t.spacing.l) {
                HStack(spacing: t.spacing.m) {
                    if let direction = question.directionEnum {
                        ChoiceGlyph(systemName: direction.symbol, isSelected: false)
                    }
                    Text(question.text)
                        .font(t.font.titleS)
                        .foregroundStyle(t.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }

                // 5 вариантов шкалы — списком, не сегментами: подписи длинные
                VStack(spacing: t.spacing.s) {
                    ForEach(vm.scale) { option in
                        ChoiceCard(text: option.text,
                                   isSelected: vm.answers[question.n] == option.value) {
                            vm.answer(option.value, for: question)
                            // мягкий автопереход: ответ выбран — двигаемся дальше сами
                            if !vm.isLastQuestion {
                                Task {
                                    try? await Task.sleep(for: .milliseconds(220))
                                    vm.nextQuestion()
                                }
                            }
                        }
                    }
                }
            }
            .id(question.n)                     // перерисовка при смене вопроса
            .transition(.opacity)
        } else if vm.isLoading {
            ProgressView().tint(t.terracotta).frame(maxWidth: .infinity)
        } else {
            EmptyStateCard(icon: "questionmark.circle",
                           title: "error.offline",
                           actionTitle: "common.retry") { vm.loadIntake() }
        }
    }

    // MARK: - Шаг 3: результат

    private var resultStep: some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            Text("onboarding.result.title")
                .font(t.font.displaySerif(24))
                .foregroundStyle(t.ink)

            if let text = vm.result?.text, !text.isEmpty {
                PageCard {
                    Text(text)
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let module = vm.recommendedModule {
                ContentCard(label: L10n("modules.start").text,
                            title: module.name,
                            text: module.passport?.intro,
                            accent: t.terracotta,
                            icon: "compass.drawing")

                AccentButton(title: "onboarding.result.start", isLoading: vm.isLoading) {
                    Task { _ = await vm.enroll(in: module.code) }
                }
            }

            // Право выбора нормативно: автоперехода быть не должно
            Text("onboarding.result.choice")
                .font(t.font.caption)
                .foregroundStyle(t.inkDim)

            GhostButton(title: "onboarding.result.other", icon: "list.bullet") {
                showModulePicker = true
            }
        }
    }

    // MARK: - Шаг 4: напоминания

    private var remindersStep: some View {
        VStack(alignment: .leading, spacing: t.spacing.l) {
            Text("onboarding.reminders.title")
                .font(t.font.displaySerif(24))
                .foregroundStyle(t.ink)
            Text("onboarding.reminders.subtitle")
                .font(t.font.body)
                .foregroundStyle(t.inkMuted)

            PageCard {
                TimeRow(title: "onboarding.reminders.morning", time: $vm.reminderMorning)
                Divider().foregroundStyle(t.border)
                TimeRow(title: "onboarding.reminders.afternoon", time: $vm.reminderAfternoon)
                Divider().foregroundStyle(t.border)
                TimeRow(title: "onboarding.reminders.evening", time: $vm.reminderEvening)
            }
        }
    }

    // MARK: - Нижняя панель

    private var bottomBar: some View {
        HStack(spacing: t.spacing.m) {
            if canGoBack {
                GhostButton(title: "common.back", icon: "chevron.left") { goBack() }
                    .frame(maxWidth: 140)
            }
            AccentButton(title: primaryTitle,
                         isLoading: vm.isLoading,
                         isDisabled: !canAdvance) { advance() }
        }
        .padding(.horizontal, t.spacing.xl)
        .padding(.vertical, t.spacing.l)
        .background(t.paper)
        .overlay(alignment: .top) {
            Divider().foregroundStyle(t.border)
        }
    }

    private var canGoBack: Bool {
        switch vm.step {
        case .language:  return false
        case .intake:    return true
        case .reminders: return false        // маршрут уже начат, назад некуда
        default:         return true
        }
    }

    private var canAdvance: Bool {
        switch vm.step {
        case .intake: return vm.canAdvanceQuestion
        case .result: return vm.recommendedModule != nil || !vm.modules.isEmpty
        default:      return true
        }
    }

    private var primaryTitle: LocalizedStringKey {
        switch vm.step {
        case .intake:    return vm.isLastQuestion ? "selfcheck.submit" : "common.next"
        case .reminders: return "common.done"
        default:         return "common.next"
        }
    }

    private func goBack() {
        switch vm.step {
        case .intake where vm.questionIndex > 0:
            vm.previousQuestion()
        case .intake:
            vm.step = .intro
        case .intro:
            vm.step = .language
        case .result:
            vm.step = .intake
        default:
            break
        }
    }

    private func advance() {
        switch vm.step {
        case .language:
            vm.step = .intro
        case .intro:
            vm.step = .intake
        case .intake:
            if vm.isLastQuestion {
                Task { await vm.submitIntake() }
            } else {
                vm.nextQuestion()
            }
        case .result:
            if let module = vm.recommendedModule {
                Task { _ = await vm.enroll(in: module.code) }
            } else {
                showModulePicker = true
            }
        case .reminders:
            Task {
                await vm.saveReminders()
                onFinish()
            }
        }
    }
}

// MARK: - Строка выбора времени

struct TimeRow: View {
    let title: LocalizedStringKey
    @Binding var time: DateComponents

    @Environment(\.theme) private var t

    private var date: Binding<Date> {
        Binding(
            get: { Calendar.current.date(from: time) ?? Date() },
            set: { time = Calendar.current.dateComponents([.hour, .minute], from: $0) }
        )
    }

    var body: some View {
        HStack {
            Text(title)
                .font(t.font.body)
                .foregroundStyle(t.ink)
            Spacer()
            DatePicker("", selection: date, displayedComponents: .hourAndMinute)
                .labelsHidden()
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Выбор маршрута вручную

struct ModulePickerSheet: View {
    let modules: [ModuleSummary]
    let onSelect: (String) -> Void

    @Environment(\.theme) private var t
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                t.paper.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: t.spacing.m) {
                        ForEach(Array(modules.enumerated()), id: \.element.id) { index, module in
                            NavigationLink {
                                ModuleDetailView(module: module) { onSelect(module.code) }
                            } label: {
                                ContentCard(label: module.code,
                                            title: module.name,
                                            text: module.passport?.intro,
                                            accent: t.terracotta,
                                            icon: Direction(rawValue: module.code)?.symbol
                                                ?? "compass.drawing")
                            }
                            .buttonStyle(.plain)
                            .staggerIn(index: index)
                        }
                    }
                    .padding(t.spacing.xl)
                }
            }
            .navigationTitle(Text("modules.title"))
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.cancel") { dismiss() }
                }
            }
        }
    }
}

/// Паспорт программы (§4): для кого, что будет, зачем, результат, границы метода.
struct ModuleDetailView: View {
    let module: ModuleSummary
    let onStart: () -> Void

    @Environment(\.theme) private var t

    var body: some View {
        ZStack {
            t.paper.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: t.spacing.xl) {
                    Text(module.name)
                        .font(t.font.displaySerif(24))
                        .foregroundStyle(t.ink)

                    if let intro = module.passport?.intro {
                        Text(intro)
                            .font(t.font.body)
                            .foregroundStyle(t.inkMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    if let forWhom = module.passport?.forWhom, !forWhom.isEmpty {
                        bulletSection(title: "modules.forWhom", items: forWhom)
                    }
                    if let gets = module.passport?.whatUserGets, !gets.isEmpty {
                        bulletSection(title: "modules.whatYouGet", items: gets)
                    }
                    if let important = module.passport?.important {
                        VStack(alignment: .leading, spacing: t.spacing.s) {
                            LabelTag(text: L10n("modules.important").text, color: t.inkMuted)
                            Text(important)
                                .font(t.font.caption)
                                .foregroundStyle(t.inkDim)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    AccentButton(title: "modules.start", action: onStart)
                }
                .padding(t.spacing.xl)
            }
        }
        .navigationBarTitleDisplayMode(.inline)
    }

    private func bulletSection(title: L10n, items: [String]) -> some View {
        VStack(alignment: .leading, spacing: t.spacing.s) {
            LabelTag(text: title.text, color: t.terracotta)
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: t.spacing.s) {
                    Circle()
                        .fill(t.terracotta.opacity(0.4))
                        .frame(width: 4, height: 4)
                        .padding(.top, 7)
                        .accessibilityHidden(true)
                    Text(item)
                        .font(t.font.body)
                        .foregroundStyle(t.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

#Preview {
    OnboardingView {}
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
