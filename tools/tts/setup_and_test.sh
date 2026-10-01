#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
  echo "Использование: ./setup_and_test.sh ИМЯ_ФАЙЛА [--only N]"
  echo "  например: ./setup_and_test.sh REAL_Week_1_4_audio_voice_scripts.txt --only 1"
  echo "  или:      ./setup_and_test.sh REAL_Неделя_2_ОЧИЩЕНО.docx --only 1"
  exit 1
fi

INPUT_FILE="$1"
shift
EXTRA_ARGS="$@"

echo "=== Настройка окружения для озвучки ==="
mkdir -p ~/tts_project
cd ~/tts_project

if [ ! -d "venv" ]; then
  echo "Создаю venv..."
  python3 -m venv venv
fi

source venv/bin/activate
echo "Ставлю зависимости..."
pip3 install --quiet python-docx requests pydub audioop-lts

if ! command -v ffmpeg &> /dev/null; then
  echo "ffmpeg не найден — ставлю через brew..."
  brew install ffmpeg
fi

echo ""
echo "=== Проверка ==="
python3 -c "import docx, requests, pydub; print('Python-зависимости: OK')"
ffmpeg -version | head -1

if [ ! -f "tts_pipeline_v3.py" ]; then
  echo "⚠️  tts_pipeline_v3.py не найден в ~/tts_project — положите его сюда."
  exit 1
fi
if [ ! -f "$INPUT_FILE" ]; then
  echo "⚠️  Файл '$INPUT_FILE' не найден в ~/tts_project — положите его сюда."
  exit 1
fi

echo ""
echo "=== Пробный разбор: $INPUT_FILE (без обращения к API) ==="
python3 tts_pipeline_v3.py --dry-run --input "$INPUT_FILE" $EXTRA_ARGS

echo ""
echo "Если разбивка выше выглядит адекватно:"
echo "  1) впишите VOICE_ID в tts_pipeline_v3.py"
echo "  2) export ELEVENLABS_API_KEY=\"ваш_ключ\""
echo "  3) python3 tts_pipeline_v3.py --input \"$INPUT_FILE\" $EXTRA_ARGS"
