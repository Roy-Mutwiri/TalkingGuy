# Build TalkingGuy.exe and publish it to the rolling "latest" GitHub release from this PC.
#   powershell -ExecutionPolicy Bypass -File installer\publish_release.ps1
# Needs the GitHub CLI logged in (gh auth login). The GitHub Actions workflow does the same automatically when
# Actions are available on the account; this script is the manual fallback. The exe only needs republishing when
# launcher\bootstrap.py changes: everything else reaches users through "Update now" (git pull) in the launcher.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_exe.ps1
if ($LASTEXITCODE -ne 0) { throw "build failed" }
$sha = (git rev-parse --short HEAD).Trim()
$notes = "Rolling build of main ($sha). Download TalkingGuy.exe, run it, and it installs or updates everything. Existing installs update from inside the app."
$exists = (gh release view latest 2>$null)
if ($LASTEXITCODE -ne 0) {
    gh release create latest dist\TalkingGuy.exe --title "Latest build" --notes $notes --latest
} else {
    gh release edit latest --notes $notes --latest | Out-Null
    gh release upload latest dist\TalkingGuy.exe --clobber
}
git tag -f latest | Out-Null
git push -f origin latest | Out-Null
Write-Host "Published: https://github.com/Roy-Mutwiri/TalkingGuy/releases/latest/download/TalkingGuy.exe"
