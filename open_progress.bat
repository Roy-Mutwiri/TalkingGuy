@echo off
REM Live build-progress board (downloads, transcription, GPU, Theo on air).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m app.stage_window --progress --x 60 --y 40
