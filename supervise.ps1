# 24/7 supervisor: keeps the teacher process and the stage window (app.stage_window, no browser) alive, forever.
#   powershell -ExecutionPolicy Bypass -File supervise.ps1 [-Offline]
param([switch]$Offline)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$stageArgs = @('-m', 'app.stage_window')      # our own window (WebView2 runtime), no browser
$pyArgs = @('-m', 'app.run'); if ($Offline) { $pyArgs += '--offline' }
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$slog = Join-Path $root "logs\supervisor.log"
function Log($m) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Write-Host $line; Add-Content -Path $slog -Value $line -Encoding UTF8 }

$teacher = $null
$restarts = 0
Log "supervisor started (offline=$Offline)"
while ($true) {
    if ($null -eq $teacher -or $teacher.HasExited) {
        if ($teacher) { Log "teacher exited with code $($teacher.ExitCode); restarting ($restarts)"; Start-Sleep -Seconds ([Math]::Min(60, 5 * ($restarts + 1))) }
        $teacher = Start-Process -FilePath $py -ArgumentList $pyArgs -WorkingDirectory $root -PassThru -WindowStyle Minimized
        $restarts++
        Log "teacher started pid $($teacher.Id)"
        Start-Sleep -Seconds 20
    }
    $win = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*app.stage_window*' -and $_.CommandLine -notlike '*--console*' }
    if (-not $win) {
        Log "stage window missing; opening"
        Start-Process -FilePath $py -ArgumentList $stageArgs -WorkingDirectory $root | Out-Null
        Start-Sleep -Seconds 5
    }
    # the live music maker (CPU, below-normal priority) keeps music/ topped up with original beats; MUSIC_MAKER=0 in .env turns it off
    $makerOff = (Test-Path (Join-Path $root ".env")) -and ((Get-Content (Join-Path $root ".env")) -match '^\s*MUSIC_MAKER\s*=\s*0')
    if (-not $makerOff) {
        $mk = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*app.voice.music_maker*' }
        if (-not $mk) {
            Log "music maker missing; starting"
            $mp = Start-Process -FilePath $py -ArgumentList @('-m', 'app.voice.music_maker') -WorkingDirectory $root -WindowStyle Hidden -PassThru
            try { $mp.PriorityClass = 'BelowNormal' } catch {}
        }
    }
    # health check: hub must answer and have a stage connected; if not for a while, restart the teacher
    try {
        $h = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:8000/health).Content | ConvertFrom-Json
        if ($h.stages -lt 1) { $script:noStage = ($script:noStage + 1) } else { $script:noStage = 0 }
        if ($script:noStage -ge 6) {
            Log "stage not connected for 3 minutes; relaunching window"
            Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*app.stage_window*' -and $_.CommandLine -notlike '*--console*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            $script:noStage = 0
        }
        $script:unhealthy = 0
    } catch {
        $script:unhealthy = ($script:unhealthy + 1)
        if ($script:unhealthy -ge 6) { Log "hub unhealthy for 3 minutes; killing teacher"; Stop-Process -Id $teacher.Id -Force -ErrorAction SilentlyContinue; $script:unhealthy = 0 }
    }
    # log rotation: keep stream.log under ~50 MB
    $lf = Join-Path $root "logs\stream.log"
    if ((Test-Path $lf) -and ((Get-Item $lf).Length -gt 50MB)) { Move-Item $lf ($lf + "." + (Get-Date -Format 'yyyyMMddHHmm')) -Force; Log "rotated stream.log" }
    Start-Sleep -Seconds 30
}
