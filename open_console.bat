@echo off
REM Opens the operator console in its own window (pause / skip / topic / question / voice / TikTok chat).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m app.stage_window --console
