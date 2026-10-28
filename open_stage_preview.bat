@echo off
REM Opens a half-size preview of the stage in its own window (the real 1080x1920 window is managed by start_stream.bat).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m app.stage_window --fit --x 40 --y 40
