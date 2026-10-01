#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Единый пайплайн под ElevenLabs v3. Понимает два формата исходников:

  A) .docx, "Аудио N. Название" + SCRIPT_FOR_VOICE + [пауза N сек] (строчными)
     + теги на каждую фразу вроде [с теплом] — формат Недели 2.

  B) .txt, "REAL / Неделя N / Аудио M" + SCRIPT_FOR_VOICE + [Пауза N сек]
     (с большой буквы) + ОДИН тег [СТИЛЬ: ...] на всё аудио — формат Недели 1.

Формат определяется автоматически по расширению файла и содержимому.
Паузы в обоих случаях становятся РЕАЛЬНОЙ тишиной при склейке — а не
многоточиями. Многоточия были нужны только для ручной вставки в Studio,
тут в этом смысла нет: пайплайн сам режет на сегменты и сам вставляет
точную тишину между ними через pydub.

Установка:
    pip install -r requirements.txt
    brew install ffmpeg   (или apt install ffmpeg в Linux/WSL)

Запуск:
    export ELEVENLABS_API_KEY="..."
    python3 tts_pipeline_v3.py --dry-run --input "файл.docx или .txt"
    python3 tts_pipeline_v3.py --input "файл.txt" --only 1
"""

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import requests
from pydub import AudioSegment

# ────────────────────────────── НАСТРОЙКИ ──────────────────────────────

OUT_DIR = Path("output")
CACHE_DIR = Path("cache")

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE_ID = "pVnrL6sighQX7hVz89cp"
MODEL_ID = "eleven_v3"

VOICE_SETTINGS = {
    "stability": 0.75,  # 0.0=Creative (живее, но менее предсказуемо) / 0.5=Natural / 1.0=Robust (стабильнее, слабее реагирует на теги)
    # было 0.5 — при низкой стабильности каждый сегмент синтезируется отдельным
    # запросом и "randomness between each generation" (см. доки ElevenLabs) даёт
    # разный голос/шум почти на каждой фразе. Подняли ближе к Robust.
    "similarity_boost": 0.80,
    "use_speaker_boost": True,
}

FADE_MS = 40
DEFAULT_GAP_MS = 500  # пауза между фразами внутри абзаца, если явно не указана

# Исходные [Пауза N сек] были рассчитаны на ручную вставку в Studio и на слух
# оказались в разы длиннее нужного — почти после каждого предложения. Сжимаем
# их этим коэффициентом, чтобы медитация не растягивалась (речь без пауз уже
# сама по себе укладывается в целевые 5-7 минут). Подбирается на слух по сэмплу.
PAUSE_SCALE = 0.3
MAX_GAP_MS = 2000  # чтобы даже самые длинные исходные паузы (6-7 сек) не тянулись

def scaled_gap_ms(seconds):
    return min(int(seconds * 1000 * PAUSE_SCALE), MAX_GAP_MS)

# Гендерно-нейтральные и орфоэпические правки. Ключи — точные фразы из
# исходников, безопасно оставлять здесь правки для всех недель разом:
# если фразы нет в конкретном файле — .replace() просто ничего не сделает.
TEXT_FIXES = {
    # --- Неделя 1, Аудио 1 (день 1) ---
    "Я ленюсь. Я потерял себя. Я должен быстрее собраться. Я обязан понять, куда идти.":
        "Я ленюсь. Я не узнаю себя. Мне нужно быстрее собраться. Мне нужно понять, куда идти.",
    "тут я опоздал, тут я должен был быть другим":
        "тут я отстаю, тут мне нужно быть другим",
    "я устал, я запутался, я не чувствую прежнего интереса":
        "мне тяжело, всё запуталось, я не чувствую прежнего интереса",
    "Не «я должен быть дальше».": "Не «мне нужно быть дальше».",
    "Не «я опоздал».": "Не «я отстаю».",
    "я начал смотреть честнее": "я начинаю смотреть честнее",
    "Я перестал называть свою паузу только ленью или слабостью.":
        "Я перестаю называть свою паузу только ленью или слабостью.",
    "Я увидел, что в ней есть сообщение.": "Я вижу, что в ней есть сообщение.",
    "Когда будешь готов, можно мягко вернуть внимание в пространство вокруг.":
        "Когда почувствуешь готовность, можно мягко вернуть внимание в пространство вокруг.",
    "пауза — это не доказательство, что ты сломан.":
        "пауза — это не доказательство того, что что-то в тебе сломалось.",
    "Например: «я устал».": "Например: «я устаю».",
    "В начале пути": "В нача́ле пути",
    "Это тоже начало.": "Это тоже нача́ло.",
    "начало спокойного движения": "нача́ло спокойного движения",
    # --- Неделя 2 ---
    "начало уже есть": "нача́ло уже есть",
    "Это начало контакта": "Это нача́ло контакта",
    "начало дороги": "нача́ло дороги",
    "маленьким началом": "маленьким нача́лом",
    "Достаточно начать": "Достаточно нача́ть",
}

def apply_fixes(text):
    for a, b in TEXT_FIXES.items():
        text = text.replace(a, b)
    return text

def clean(s):
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{2,}", "\n", s).strip()

# ───────────────────────── ПЕРЕВОД ТЕГОВ В v3 ─────────────────────────

# Точные теги "на каждую фразу" — формат Недели 2
TAG_MAP = {
    "спокойно, тепло, медленно": "calm, warm, slow pace",
    "мягче": "softer", "тише": "quietly",
    "утвердительно": "gently affirming", "вопросительно": "questioning tone",
    "вопросительно, мягко": "softly questioning", "с теплом": "warmly",
    "с опорой": "steady, reassuring", "чуть медленнее": "slightly slower",
    "медленнее": "slower", "утвердительно, с теплом": "warmly reassuring",
    "утвердительно, с опорой": "steady and reassuring",
    "тише, бережно": "quietly, tenderly", "мягко, с опорой": "gently, steady",
    "утвердительно, мягко": "gently affirming",
    "чуть глубже": "slightly deeper tone", "чуть тише": "slightly quieter",
    "мягко": "gently",
}
WORD_MAP = {
    "спокойно": "calm", "тепло": "warm", "медленно": "slow",
    "мягче": "softer", "мягко": "gently", "тише": "quietly",
    "утвердительно": "affirming", "вопросительно": "questioning",
    "с теплом": "warm", "с опорой": "steady", "бережно": "tenderly",
    "глубже": "deeper", "чуть": "slightly", "медленнее": "slower",
}

def translate_tag(ru_tag):
    ru_tag = ru_tag.strip()
    if ru_tag in TAG_MAP:
        return TAG_MAP[ru_tag]
    parts = [p.strip() for p in ru_tag.split(",")]
    return ", ".join(WORD_MAP.get(p, p) for p in parts)

# Один общий [СТИЛЬ: ...] на всё аудио — формат Недели 1.
# Точные соответствия по 4 вариантам, что реально встречаются в файле;
# если попадётся новый — соберём короткий тег эвристикой по словам.
STYLE_MAP = {
    "спокойный, тёплый, медленный, терапевтический. Голос мягкий, без давления, без драматизации. Темп ниже среднего. Важные фразы произносить чуть медленнее.":
        "calm, warm, slow, gentle",
    "спокойный, тёплый, медленный, терапевтический. Голос мягкий. Темп ниже среднего. Без драматизации. Важные фразы произносить с лёгким замедлением.":
        "calm, warm, slow, gentle",
    "спокойный, тёплый, медленный, терапевтический. Голос уверенно-мягкий. Без давления. Темп ниже среднего. На фразах выбора делать чуть больше воздуха.":
        "calm, warm, slow, confident yet gentle",
    "спокойный, тёплый, медленный, завершающий. Голос поддерживающий, без торжественности и без давления. Финальное аудио чуть длиннее. Паузы выдерживать полностью.":
        "calm, warm, slow, supportive",
}

def translate_style(style_ru):
    style_ru = style_ru.strip()
    if style_ru in STYLE_MAP:
        return STYLE_MAP[style_ru]
    # эвристика на случай нового текста стиля: берём ключевые слова
    found = [eng for ru, eng in WORD_MAP.items() if ru in style_ru.lower()]
    return ", ".join(dict.fromkeys(found)) or "calm, warm, slow"

# ──────────────────────── ФОРМАТ A: Неделя 2 (.docx) ────────────────────────

def read_scripts_docx(path):
    from docx import Document
    doc = Document(path)
    lines = [p.text.strip() for p in doc.paragraphs]
    scripts, title, buf, capturing = [], None, [], False
    for line in lines:
        m = re.match(r"^Аудио (\d+)\.\s*(.+)$", line)
        if m:
            if capturing and buf:
                scripts.append((title, "\n".join(buf)))
            title, buf, capturing = f"{m.group(1)}. {m.group(2)}", [], False
            continue
        if line == "SCRIPT_FOR_VOICE":
            capturing, buf = True, []
            continue
        if capturing and line.startswith(("Привязка", "Смысл аудио", "Основная ассоциация")):
            capturing = False
            continue
        if capturing:
            buf.append(line)
    if capturing and buf:
        scripts.append((title, "\n".join(buf)))
    return scripts

TOKEN_RE = re.compile(r"\[([^\]]*)\]")

def segment_docx_audio(text):
    text = apply_fixes(text)
    active_tag, segments, pos = None, [], 0
    for m in TOKEN_RE.finditer(text):
        chunk = text[pos:m.start()].strip()
        raw = m.group(1)
        pause_m = re.match(r"пауза\s*(\d+)\s*сек", raw, re.I)
        if chunk:
            segments.append({"text": clean(chunk), "tag": active_tag, "gap_ms": 0})
        if pause_m:
            gap = scaled_gap_ms(int(pause_m.group(1)))
            if segments:
                segments[-1]["gap_ms"] += gap
        else:
            active_tag = translate_tag(raw)
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        segments.append({"text": clean(tail), "tag": active_tag, "gap_ms": 0})
    return _split_paragraphs(segments)

# ──────────────────────── ФОРМАТ B: Неделя 1 (.txt) ────────────────────────

def read_scripts_txt(path):
    raw = Path(path).read_text(encoding="utf-8")
    parts = re.split(r"(?=^REAL / .+/ Аудио \d+\s*$)", raw, flags=re.M)
    scripts = []
    for part in parts:
        header_m = re.match(r"^REAL / (.+?) / Аудио (\d+)\s*$", part, re.M)
        if not header_m:
            continue
        title = f"{header_m.group(1)}, Аудио {header_m.group(2)}"
        if "SCRIPT_FOR_VOICE" not in part:
            continue
        body = part.split("SCRIPT_FOR_VOICE", 1)[1]
        # обрезаем случайный "разделитель-линейку" перед следующим блоком
        body = re.sub(r"\n-{5,}\s*$", "", body).strip()
        scripts.append((title, body))
    return scripts

def segment_txt_audio(text):
    text = apply_fixes(text)
    style_m = re.search(r"\[СТИЛЬ:\s*([^\]]+)\]", text)
    v3_tag = translate_style(style_m.group(1)) if style_m else "calm, warm, slow"
    text = re.sub(r"\[СТИЛЬ:[^\]]+\]\s*", "", text)

    segments, pos = [], 0
    for m in re.finditer(r"\[Пауза\s*(\d+)\s*сек\]", text, re.I):
        chunk = text[pos:m.start()].strip()
        if chunk:
            segments.append({"text": clean(chunk), "tag": v3_tag, "gap_ms": 0})
        gap = scaled_gap_ms(int(m.group(1)))
        if segments:
            segments[-1]["gap_ms"] += gap
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        segments.append({"text": clean(tail), "tag": v3_tag, "gap_ms": 0})
    return _split_paragraphs(segments)

# ──────────────────────────── общее ────────────────────────────

def _split_paragraphs(segments):
    out = []
    for s in segments:
        parts = [p.strip() for p in s["text"].split("\n") if p.strip()]
        for i, p in enumerate(parts):
            last = i == len(parts) - 1
            out.append({"text": p, "tag": s["tag"],
                       "gap_ms": s["gap_ms"] if last else DEFAULT_GAP_MS})
    return out

def load_and_segment(path):
    path = Path(path)
    if path.suffix.lower() == ".docx":
        scripts = read_scripts_docx(path)
        return [(t, segment_docx_audio(raw)) for t, raw in scripts]
    else:
        scripts = read_scripts_txt(path)
        return [(t, segment_txt_audio(raw)) for t, raw in scripts]

def text_with_tag(seg, is_first=False):
    # на самой первой фразе аудио тег стиля перед текстом провоцирует у v3
    # неестественный взлёт интонации вверх (нет предыдущего аудио-контекста) —
    # для первого сегмента отдаём текст без тега, дальше тег как обычно.
    if not seg["tag"] or is_first:
        return seg["text"]
    return f"[{seg['tag']}] {seg['text']}"

# ────────────────────────────── СИНТЕЗ ──────────────────────────────

URL = "https://api.elevenlabs.io/v1/text-to-speech/{vid}"

def synth(text, prev_text, next_text, retries=4):
    payload = {
        "text": text, "model_id": MODEL_ID, "voice_settings": VOICE_SETTINGS,
    }
    # eleven_v3 пока не принимает previous_text/next_text вообще (даже null) — API 400.
    if MODEL_ID != "eleven_v3":
        payload["previous_text"] = prev_text or None
        payload["next_text"] = next_text or None
    headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
    for attempt in range(retries):
        r = requests.post(URL.format(vid=VOICE_ID), json=payload, headers=headers, timeout=120)
        if r.status_code == 200:
            return r.content
        if r.status_code == 429:
            wait = 2 ** attempt * 5
            print(f"      rate limit, жду {wait}s")
            time.sleep(wait)
            continue
        raise RuntimeError(f"API {r.status_code}: {r.text[:300]}")
    raise RuntimeError("не удалось после нескольких попыток")

def cache_key(text):
    blob = f"{VOICE_ID}|{MODEL_ID}|{VOICE_SETTINGS}|{text}"
    return hashlib.sha256(blob.encode()).hexdigest()[:20]

def build(title, segs, dry_run=False, redo=None, limit=None):
    CACHE_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    if limit:
        segs = segs[:limit]
        title = f"{title} (первые {limit})"
    texts = [text_with_tag(s, is_first=(i == 0)) for i, s in enumerate(segs)]
    total_chars = sum(len(t) for t in texts)
    total_gap = sum(s["gap_ms"] for s in segs) / 1000
    print(f"\n=== {title}")
    print(f"    сегментов: {len(segs)}  символов: {total_chars}  тишины: {total_gap:.0f} с")

    if dry_run:
        for i, s in enumerate(segs[:8]):
            tag = f"[{s['tag']}] " if s["tag"] else ""
            print(f"    [{i:03d}] +{s['gap_ms']}мс  {tag}{s['text'][:60]}...")
        print(f"    ... ещё {max(0, len(segs) - 8)} сегментов")
        return

    track = AudioSegment.silent(duration=0)
    for i, s in enumerate(segs):
        full_text = texts[i]
        key = cache_key(full_text)
        f = CACHE_DIR / f"{key}.mp3"
        if not f.exists() or (redo is not None and i == redo):
            prev = segs[i - 1]["text"] if i > 0 else None
            nxt = segs[i + 1]["text"] if i < len(segs) - 1 else None
            print(f"    [{i:03d}/{len(segs)}] синтез: {full_text[:60]}...")
            f.write_bytes(synth(full_text, prev, nxt))
            time.sleep(0.3)
        else:
            print(f"    [{i:03d}/{len(segs)}] из кэша")
        piece = AudioSegment.from_mp3(f).fade_in(FADE_MS).fade_out(FADE_MS)
        track += piece
        if s["gap_ms"]:
            track += AudioSegment.silent(duration=s["gap_ms"])

    track = track.normalize(headroom=3.0) + AudioSegment.silent(duration=1500)
    safe = re.sub(r"[^\w\-]+", "_", title)[:60]
    out = OUT_DIR / f"audio_{safe}.mp3"
    track.export(out, format="mp3", bitrate="192k", tags={"title": title})
    print(f"    ✓ {out}  ({len(track) / 60000:.1f} мин)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help=".docx (Неделя 2) или .txt (Неделя 1)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", type=int)
    ap.add_argument("--redo", type=int)
    ap.add_argument("--limit", type=int, help="озвучить только первые N сегментов (для теста)")
    args = ap.parse_args()

    if not args.dry_run:
        if not API_KEY:
            sys.exit("Не задан ELEVENLABS_API_KEY")
        if VOICE_ID.startswith("ПОДСТАВЬТЕ"):
            sys.exit("Впишите VOICE_ID клонированного голоса")

    scripts = load_and_segment(args.input)
    print(f"Найдено скриптов: {len(scripts)}")
    for idx, (title, segs) in enumerate(scripts, 1):
        if args.only and idx != args.only:
            continue
        build(title, segs, dry_run=args.dry_run, redo=args.redo, limit=args.limit)

if __name__ == "__main__":
    main()
