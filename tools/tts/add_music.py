#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерирует фоновую музыку через ElevenLabs Music API (POST /v1/music) под
длительность готового голосового трека и накладывает её тише под голос.

Запуск:
    export ELEVENLABS_API_KEY="..."
    python3 add_music.py output/audio_Неделя_1_Аудио_1_clean.mp3
    python3 add_music.py output/audio_Неделя_1_Аудио_1_clean.mp3 --prompt "..." --volume -22
"""

import argparse
import io
import os
from pathlib import Path

import requests
from pydub import AudioSegment

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
URL = "https://api.elevenlabs.io/v1/music"

DEFAULT_PROMPT = (
    "calm ambient meditation background music, soft warm pads, gentle, "
    "no drums, no melody hooks, no vocals, slow, unobtrusive, looping feel, "
    "great production quality"
)
FADE_MS = 3000

def compose_music(duration_ms: int, prompt: str) -> bytes:
    payload = {
        "prompt": prompt,
        "music_length_ms": max(3000, min(duration_ms, 600000)),
        "force_instrumental": True,
    }
    headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
    r = requests.post(URL, json=payload, headers=headers, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"API {r.status_code}: {r.text[:300]}")
    return r.content

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voice_mp3")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--volume", type=float, default=-20.0, help="дБ музыки относительно голоса")
    ap.add_argument("--regenerate", action="store_true", help="заново вызвать Music API вместо кэша")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("Не задан ELEVENLABS_API_KEY")

    voice_path = Path(args.voice_mp3)
    voice = AudioSegment.from_file(voice_path)

    # кэшируем сырую музыку на диск, чтобы подбор громкости не тратил кредиты API повторно
    raw_music_path = voice_path.with_name(voice_path.stem + "_music_raw.mp3")
    if raw_music_path.exists() and not args.regenerate:
        print(f"Использую закэшированную музыку {raw_music_path}")
        music = AudioSegment.from_file(raw_music_path)
    else:
        print(f"Генерирую музыку под {len(voice) / 1000:.1f} c...")
        music_bytes = compose_music(len(voice), args.prompt)
        raw_music_path.write_bytes(music_bytes)
        music = AudioSegment.from_file(io.BytesIO(music_bytes))

    # растягиваем/обрезаем музыку под длительность голоса и приглушаем её
    if len(music) < len(voice):
        loops = int(len(voice) / len(music)) + 1
        music = music * loops
    music = music[: len(voice)] + args.volume
    music = music.fade_in(FADE_MS).fade_out(FADE_MS)

    mixed = voice.overlay(music)
    out = voice_path.with_name(voice_path.stem + "_music.mp3")
    mixed.export(out, format="mp3", bitrate="192k")
    print(f"✓ {out}")

if __name__ == "__main__":
    main()
