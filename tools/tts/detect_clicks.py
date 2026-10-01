#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ищет в mp3 подозрительные щелчки/поп-артефакты — короткие всплески громкости,
резко выделяющиеся на фоне соседних кадров (не путать с обычными
согласными/громкими словами, которые держатся дольше одного кадра).
Не гарантирует 100% находку всех "пуков", но резко сокращает, что слушать
руками — вместо 10 минут проверяешь пару десятков коротких моментов.

Запуск:
    python3 detect_clicks.py output/audio_Неделя_1_Аудио_1_clean.mp3
"""

import sys
from pathlib import Path

import numpy as np
from pydub import AudioSegment

FRAME_MS = 10
HOP_MS = 5
CONTEXT_MS = 300     # окно для локальной "нормальной" громкости вокруг кадра
GUARD_MS = 30        # кадры вплотную к анализируемому не учитываем в базовой линии
RATIO_THRESHOLD = 4.5
MIN_ABS_LEVEL = 0.02  # игнорируем всплески в почти полной тишине
MERGE_MS = 80         # соседние срабатывания в пределах этого окна — одно событие
TOP_N = 30

def fmt_ts(ms):
    s = ms / 1000
    return f"{int(s // 60)}:{s % 60:05.2f}"

def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python3 detect_clicks.py путь/к/файлу.mp3")
    path = Path(sys.argv[1])
    audio = AudioSegment.from_file(path).set_channels(1)
    sr = audio.frame_rate
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    samples /= float(1 << (8 * audio.sample_width - 1))

    frame_len = int(sr * FRAME_MS / 1000)
    hop_len = int(sr * HOP_MS / 1000)
    n_frames = max(0, (len(samples) - frame_len) // hop_len + 1)
    energy = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = samples[i * hop_len: i * hop_len + frame_len]
        energy[i] = float(np.sqrt(np.mean(chunk ** 2)) + 1e-9)

    ctx_frames = int(CONTEXT_MS / HOP_MS)
    guard_frames = max(1, int(GUARD_MS / HOP_MS))

    events = []
    for i in range(n_frames):
        lo, hi = max(0, i - ctx_frames), min(n_frames, i + ctx_frames)
        left = energy[lo:max(lo, i - guard_frames)]
        right = energy[min(hi, i + guard_frames):hi]
        neighborhood = np.concatenate([left, right]) if (len(left) or len(right)) else energy[lo:hi]
        if len(neighborhood) < 5:
            continue
        baseline = float(np.median(neighborhood))
        if energy[i] < MIN_ABS_LEVEL:
            continue
        ratio = energy[i] / (baseline + 1e-6)
        if ratio >= RATIO_THRESHOLD:
            ts_ms = i * hop_len / sr * 1000
            events.append((ts_ms, ratio))

    # схлопываем соседние срабатывания в одно событие (берём с максимальным ratio)
    merged = []
    for ts_ms, ratio in sorted(events):
        if merged and ts_ms - merged[-1][0] <= MERGE_MS:
            if ratio > merged[-1][1]:
                merged[-1] = (ts_ms, ratio)
        else:
            merged.append((ts_ms, ratio))

    merged.sort(key=lambda x: -x[1])
    print(f"Длительность: {fmt_ts(len(audio))}, найдено кандидатов: {len(merged)}")
    for ts_ms, ratio in merged[:TOP_N]:
        print(f"  {fmt_ts(ts_ms)}  (всплеск x{ratio:.1f})")

if __name__ == "__main__":
    main()
