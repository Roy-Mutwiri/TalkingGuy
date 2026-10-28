"""Start, stop and watch the stream from the launcher.

The stream itself is `supervise.ps1` (24/7 supervisor) which runs `app.run` (hub + teacher) and `app.stage_window`
(the window LIVE Studio captures). The launcher starts the supervisor hidden and stops the whole family on request.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

from .common import CREATE_NO_WINDOW, HUB, ROOT, VENV_PY, VENV_PYW, child_env

try:
    import psutil
except Exception:  # noqa: BLE001
    psutil = None  # type: ignore[assignment]

_MARKERS = ("supervise.ps1", "app.run", "app.stage_window")


def _ours(cmdline: list[str] | None) -> bool:
    if not cmdline:
        return False
    text = " ".join(cmdline)
    return str(ROOT).lower() in text.lower() or any(m in text for m in ("-m app.run", "app.stage_window", "supervise.ps1"))


def stream_processes() -> list:
    """Our stream processes (supervisor, teacher, stage/console windows), never the launcher itself."""
    if psutil is None:
        return []
    me = os.getpid()
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            cl = p.info.get("cmdline") or []
            if any(m in " ".join(cl) for m in _MARKERS) and ("-m launcher" not in " ".join(cl)) and _ours(cl):
                out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def teacher_running() -> bool:
    return any("-m app.run" in " ".join(p.info.get("cmdline") or []) for p in stream_processes())


def start_stream(offline: bool = False) -> subprocess.Popen:
    (ROOT / "logs").mkdir(exist_ok=True)
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "supervise.ps1")]
    if offline:
        args.append("-Offline")
    return subprocess.Popen(args, cwd=str(ROOT), env=child_env(), creationflags=CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_stream() -> int:
    """Kill supervisor first (so it does not restart the teacher), then the rest. Returns how many were stopped."""
    procs = stream_processes()
    sup = [p for p in procs if "supervise.ps1" in " ".join(p.info.get("cmdline") or [])]
    rest = [p for p in procs if p not in sup]
    n = 0
    for group in (sup, rest):
        for p in group:
            try:
                p.kill()
                n += 1
            except Exception:  # noqa: BLE001
                pass
    if psutil is not None and (sup or rest):
        psutil.wait_procs(sup + rest, timeout=5)
    return n


def hub_health() -> dict | None:
    try:
        with urllib.request.urlopen(f"{HUB}/health", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def open_console() -> None:
    subprocess.Popen([str(VENV_PYW), "-m", "app.stage_window", "--console"], cwd=str(ROOT), env=child_env(), creationflags=CREATE_NO_WINDOW)


def open_stage_preview() -> None:
    subprocess.Popen([str(VENV_PYW), "-m", "app.stage_window", "--fit", "--framed"], cwd=str(ROOT), env=child_env(), creationflags=CREATE_NO_WINDOW)


def open_folder(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]


def tail_log(n: int = 60) -> str:
    p = ROOT / "logs" / "stream.log"
    if not p.exists():
        return "(no log yet)"
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 64_000))
            data = f.read().decode("utf-8", errors="replace")
        return "\n".join(data.splitlines()[-n:])
    except OSError:
        return "(log unreadable)"


def venv_ready() -> bool:
    return VENV_PY.exists()
