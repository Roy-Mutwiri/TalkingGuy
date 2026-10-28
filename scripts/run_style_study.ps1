# Detached runner for the host-technique study (hours): waits for the Python deps, then runs every stage.
#   powershell -ExecutionPolicy Bypass -File scripts\run_style_study.ps1
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$out = Join-Path $root "training\streamer_style"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out "run.out"
$env:PYTHONIOENCODING = "utf-8"
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') runner started" | Add-Content $log
$deadline = (Get-Date).AddMinutes(40)
while ((Get-Date) -lt $deadline) {
    & $py -c "import faster_whisper, yt_dlp" 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 20
}
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') deps ready, starting pipeline" | Add-Content $log
& $py (Join-Path $root "scripts\style_from_streams.py") --urls (Join-Path $out "urls.txt") --stage all --demos 150 *>> $log
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pipeline exit $LASTEXITCODE" | Add-Content $log
