#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Прогоняет готовый mp3 через ElevenLabs Audio Isolation API (POST /v1/audio-isolation),
убирает шум/щелчки и сохраняет результат рядом с исходным файлом с суффиксом _clean.

Запуск:
    export ELEVENLABS_API_KEY="..."
    python3 clean_audio.py output/audio_Неделя_1_Аудио_1.mp3
"""

import io
import os
import sys
from pathlib import Path

import requests
from pydub import AudioSegment

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
URL = "https://api.elevenlabs.io/v1/audio-isolation"

def isolate(path: Path) -> Path:
    data = path.read_bytes()
    headers = {"xi-api-key": API_KEY}
    files = {"audio": (path.name, data, "audio/mpeg")}
    r = requests.post(URL, headers=headers, files=files, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"API {r.status_code}: {r.text[:300]}")
    # формат ответа не документирован явно — распознаём через ffmpeg вместо
    # жёсткой привязки к mp3/wav
    audio = AudioSegment.from_file(io.BytesIO(r.content))
    out = path.with_name(path.stem + "_clean.mp3")
    audio.export(out, format="mp3", bitrate="192k")
    return out

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Использование: python3 clean_audio.py путь/к/файлу.mp3")
    if not API_KEY:
        sys.exit("Не задан ELEVENLABS_API_KEY")
    src = Path(sys.argv[1])
    out = isolate(src)
    print(f"✓ {out}")
