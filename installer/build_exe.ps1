# Builds dist\TalkingGuy.exe from launcher\bootstrap.py (standard library only, so the exe stays small).
#   powershell -ExecutionPolicy Bypass -File installer\build_exe.ps1
# Needs: .venv with pyinstaller (pip install pyinstaller). The GitHub workflow runs the same command.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name TalkingGuy `
    --distpath dist --workpath build --specpath build `
    --icon NONE `
    launcher\bootstrap.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Get-Item dist\TalkingGuy.exe | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
