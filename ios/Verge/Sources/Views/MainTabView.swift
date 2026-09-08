import SwiftUI

struct MainTabView: View {
    @State private var selectedTab: MainTab = .today
    @Environment(\.theme) private var t

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                TodayView()
            }
            .tabItem { Label("tab.today", systemImage: "sun.horizon") }
            .tag(MainTab.today)

            NavigationStack {
                // Прокинутое замыкание — приём Rhythmos: пустое состояние истории
                // умеет перебросить на «Сегодня», не зная о TabView.
                HistoryView { selectedTab = .today }
            }
            .tabItem { Label("tab.history", systemImage: "book.closed") }
            .tag(MainTab.history)

            NavigationStack {
                PathView { selectedTab = .today }
            }
            .tabItem { Label("tab.path", systemImage: "chart.line.uptrend.xyaxis") }
            .tag(MainTab.path)

            NavigationStack {
                MeView()
            }
            .tabItem { Label("tab.me", systemImage: "person.crop.circle") }
            .tag(MainTab.me)
        }
        .tint(t.terracotta)
    }
}

enum MainTab {
    case today
    case history
    case path
    case me
}

#Preview {
    MainTabView()
        .environmentObject(AuthViewModel())
        .environmentObject(LanguageStore.shared)
        .environment(\.theme, .warm)
}
