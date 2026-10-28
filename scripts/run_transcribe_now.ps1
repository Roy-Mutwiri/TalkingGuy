# Parallel transcriber: transcribes whatever audio has finished downloading, skipping files already done.
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "scripts\style_from_streams.py") --stage transcribe *>> (Join-Path $root "training\streamer_style\transcribe.out")
