"""Shared helpers for the launcher: paths, .env editing, child processes, machine checks.

The launcher runs with the project's own virtual environment (`.venv\\Scripts\\pythonw.exe -m launcher`), started
either by TalkingGuy.exe (the installer/bootstrap) or by a developer from a checkout.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
VENV_PY = VENV / "Scripts" / "python.exe"
VENV_PYW = VENV / "Scripts" / "pythonw.exe"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
LOGS = ROOT / "logs"
TOOLS = Path(os.getenv("TTG_TOOLS") or (Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "TalkingGuy" / "tools"))
REPO_URL = "https://github.com/Roy-Mutwiri/TalkingGuy.git"
HUB = "http://127.0.0.1:8000"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
Log = Callable[[str], None]


# ---------------------------------------------------------------- environment for child processes
def child_env() -> dict[str, str]:
    """PATH with our portable tools (ffmpeg, git) in front, so the app finds them without a system install."""
    env = os.environ.copy()
    extra = [TOOLS / "ffmpeg" / "bin", TOOLS / "git" / "cmd", TOOLS / "git" / "mingw64" / "bin"]
    env["PATH"] = os.pathsep.join([str(p) for p in extra if p.exists()] + [env.get("PATH", "")])
    env["TTG_TOOLS"] = str(TOOLS)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run(cmd: list[str], *, cwd: Path | None = None, timeout: float | None = 120, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd or ROOT), env=child_env(), capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=check, creationflags=CREATE_NO_WINDOW)


def stream_cmd(cmd: list[str], log: Log, *, cwd: Path | None = None) -> int:
    """Run a long command and forward each output line to the log. Returns the exit code."""
    log("> " + " ".join(str(c) for c in cmd))
    p = subprocess.Popen(cmd, cwd=str(cwd or ROOT), env=child_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if line:
            log(line)
    return p.wait()


def which(name: str) -> str | None:
    return shutil.which(name, path=child_env()["PATH"])


# ---------------------------------------------------------------- .env
_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def read_env() -> dict[str, str]:
    """Keys and values from .env (comments stripped, inline `   # ...` comments removed)."""
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _ENV_LINE.match(raw)
        if not m or raw.lstrip().startswith("#"):
            continue
        val = m.group(2)
        if "   #" in val:
            val = val.split("   #", 1)[0].rstrip()
        out[m.group(1)] = val.strip().strip('"').strip("'")
    return out


def write_env(updates: dict[str, str]) -> None:
    """Set keys in .env in place (keeps comments and order); missing keys are appended. Creates .env from the example."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else "", encoding="utf-8")
    lines = ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    done: set[str] = set()
    for i, raw in enumerate(lines):
        m = _ENV_LINE.match(raw)
        if m and not raw.lstrip().startswith("#") and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            done.add(m.group(1))
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


# ---------------------------------------------------------------- downloads
def download(url: str, dest: Path, log: Log, label: str | None = None) -> Path:
    """Download with a progress line every ~5%. Resumes nothing (files are small-to-medium); overwrites dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "TalkingGuy-launcher"})
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, -1
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                pct = got * 100 // total
                if pct // 5 != last:
                    last = pct // 5
                    log(f"{label or dest.name}: {pct}% ({got / 1e6:.0f} / {total / 1e6:.0f} MB)")
    tmp.replace(dest)
    return dest


def unzip(zip_path: Path, dest: Path, strip_top: bool = False) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        top = names[0].split("/")[0] if strip_top and names and "/" in names[0] else None
        for n in names:
            target_rel = n[len(top) + 1:] if top and n.startswith(top + "/") else n
            if not target_rel or target_rel.endswith("/"):
                continue
            target = dest / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


# ---------------------------------------------------------------- machine checks
def gpu_name() -> str | None:
    try:
        r = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], timeout=8)
        name = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None
        return name
    except Exception:  # noqa: BLE001
        return None


def has_ffmpeg() -> bool:
    return which("ffmpeg") is not None


def has_git() -> bool:
    return which("git") is not None


def has_webview2() -> bool:
    if os.name != "nt":
        return False
    import winreg

    keys = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")]
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def audio_outputs() -> list[str]:
    """Names of output devices (WASAPI preferred, de-duplicated), '' on failure."""
    try:
        import sounddevice as sd

        names: list[str] = []
        for dev in sd.query_devices():
            if dev.get("max_output_channels", 0) > 0 and dev["name"] not in names:
                names.append(dev["name"])
        return names
    except Exception:  # noqa: BLE001
        return []


def has_vbcable() -> bool:
    return any("cable input" in n.lower() for n in audio_outputs())


def gpu_voice_installed() -> bool:
    try:
        r = run([str(VENV_PY), "-c", "import torch, chatterbox; print(torch.cuda.is_available())"], timeout=90)
        return r.returncode == 0 and "True" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def claude_cli() -> Path | None:
    """The Claude Code CLI bundled with the Agent SDK inside the venv (used for the claude.ai login option)."""
    cands = list((VENV / "Lib" / "site-packages" / "claude_agent_sdk" / "_bundled").glob("claude*.exe")) if VENV.exists() else []
    if cands:
        return cands[0]
    w = which("claude")
    return Path(w) if w else None


def python_in_venv_ok() -> bool:
    return VENV_PY.exists()


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)
