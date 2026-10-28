@echo off
REM Starts the 24/7 supervisor: it launches the AI teacher and the stage window and restarts
REM either one whenever it dies. Close this window to stop everything.
REM Usage:  start_stream.bat             (full mode, needs ANTHROPIC_API_KEY in .env)
REM         start_stream.bat --offline   (no Claude calls, template lessons)
cd /d "%~dp0"
if not exist .env (
  echo .env not found. Copy .env.example to .env and fill in your keys.
)
set OFFLINE=
if /I "%~1"=="--offline" set OFFLINE=-Offline
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0supervise.ps1" %OFFLINE%
