import AVFoundation
import Foundation
import Speech

/// Диктовка ответов. Локаль распознавания приходит извне и следует выбранному языку —
/// в Rhythmos она была прибита к `ru-RU`.
@MainActor
final class SpeechRecorder: NSObject, ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var isRecording = false
    @Published private(set) var errorMessage: String?

    private var recognizer: SFSpeechRecognizer?
    private let audioEngine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    func start(locale: Locale, existing: String) {
        errorMessage = nil
        transcript = existing
        recognizer = SFSpeechRecognizer(locale: locale) ?? SFSpeechRecognizer()

        guard recognizer?.isAvailable == true else {
            errorMessage = L10n("error.offline").text
            return
        }

        SFSpeechRecognizer.requestAuthorization { [weak self] speechStatus in
            guard let self else { return }
            AVAudioApplication.requestRecordPermission { micGranted in
                Task { @MainActor in
                    guard speechStatus == .authorized, micGranted else {
                        self.errorMessage = String(
                            localized: "Разрешите микрофон и распознавание речи в настройках.")
                        return
                    }
                    self.beginRecording()
                }
            }
        }
    }

    func stop() {
        guard isRecording || audioEngine.isRunning else { return }
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func beginRecording() {
        if audioEngine.isRunning { stop() }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            self.request = request

            let input = audioEngine.inputNode
            let format = input.outputFormat(forBus: 0)
            input.removeTap(onBus: 0)
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
                request.append(buffer)
            }

            audioEngine.prepare()
            try audioEngine.start()
            isRecording = true

            task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let result {
                        self.transcript = result.bestTranscription.formattedString
                    }
                    if error != nil || result?.isFinal == true {
                        self.stop()
                    }
                }
            }
        } catch {
            errorMessage = error.localizedDescription
            stop()
        }
    }
}
