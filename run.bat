@echo off
REM One-command launcher for AI Jukebox (Windows).
REM   run.bat              -> starts on http://127.0.0.1:7860
REM   set AIJ_SHARE=1 && run.bat -> also public gradio.live link (in the log)
cd /d "%~dp0"

if not exist .venv (
  echo ==^> Creating virtual environment and installing requirements...
  python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
)

if not exist .env (
  echo ==^> No .env found - copying .env.example ^(edit AIJ_API_KEY^).
  copy /Y .env.example .env >nul
)

echo ==^> Starting AI Jukebox... ^(Ctrl-C to stop^)
.venv\Scripts\python app.py
