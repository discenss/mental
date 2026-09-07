import SwiftUI

/// Появление списком: каждый следующий элемент чуть позже предыдущего.
struct StaggerModifier: ViewModifier {
    let index: Int
    let delay: Double
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false

    func body(content: Content) -> some View {
        content
            .opacity(visible ? 1 : 0)
            .offset(y: visible ? 0 : 14)
            .animation(reduceMotion ? nil
                       : .spring(duration: 0.4, bounce: 0.15).delay(Double(index) * delay),
                       value: visible)
            .task { visible = true }
    }
}

extension View {
    func staggerIn(index: Int, delay: Double = 0.06) -> some View {
        modifier(StaggerModifier(index: index, delay: delay))
    }
}

struct SlideUpModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible = false

    func body(content: Content) -> some View {
        content
            .opacity(visible ? 1 : 0)
            .offset(y: visible ? 0 : 24)
            .animation(reduceMotion ? nil : .spring(duration: 0.5, bounce: 0.15), value: visible)
            .task { visible = true }
    }
}

extension View {
    func slideUp() -> some View { modifier(SlideUpModifier()) }
}

struct PulseModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(pulsing ? 1.03 : 1.0)
            .animation(reduceMotion ? nil
                       : .easeInOut(duration: 1.6).repeatForever(autoreverses: true),
                       value: pulsing)
            .task { pulsing = true }
    }
}

extension View {
    func pulse() -> some View { modifier(PulseModifier()) }
}
