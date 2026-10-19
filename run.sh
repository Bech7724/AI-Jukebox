#!/usr/bin/env bash
# One-command launcher for AI Jukebox (macOS / Linux).
#   bash run.sh            -> starts on http://127.0.0.1:7860
#   AIJ_SHARE=1 bash run.sh -> also exposes a public gradio.live link (printed
#                              in the log; dies with the process, expires ~1 wk)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> Creating virtual environment and installing requirements…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "==> No .env found — copying .env.example (edit it with your class key: AIJ_API_KEY)."
  [ -f .env.example ] && cp .env.example .env
fi

echo "==> Starting AI Jukebox… (press Ctrl-C to stop)"
exec .venv/bin/python app.py
