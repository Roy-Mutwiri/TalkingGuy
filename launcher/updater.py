"""Updates from the GitHub repo without reinstalling: the app folder is a git checkout.

- `check()`   : fetch, and say how many commits behind/ahead the local copy is.
- `update()`  : stop the stream, pull (fast-forward only, your own edits are stashed and restored), reinstall
                packages if requirements changed, restart the stream if it was running.
The exe (TalkingGuy.exe) never needs replacing: it only starts this code from the checkout.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .common import ROOT, VENV_PY, Log, has_git, run, stream_cmd
from .process import start_stream, stop_stream, teacher_running

REQ_FILES = ("requirements.txt", "requirements-gpu.txt")


@dataclass
class UpdateState:
    ok: bool
    behind: int = 0
    ahead: int = 0
    local: str = ""
    remote: str = ""
    message: str = ""


def _git(*args: str, timeout: float = 120):
    return run(["git", *args], timeout=timeout)


def is_checkout() -> bool:
    return (ROOT / ".git").exists() and has_git()


def current_version() -> str:
    if not is_checkout():
        return "not a git checkout"
    r = _git("log", "-1", "--date=format:%Y-%m-%d %H:%M", "--format=%h  %ad  %s", timeout=20)
    return r.stdout.strip()[:90] if r.returncode == 0 else "unknown"


def check() -> UpdateState:
    if not is_checkout():
        return UpdateState(False, message="This copy is not a git checkout (or git is missing); install from TalkingGuy.exe to get updates.")
    f = _git("fetch", "--quiet", "origin", timeout=90)
    if f.returncode != 0:
        return UpdateState(False, message="Could not reach GitHub: " + f.stderr.strip()[-160:])
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=20).stdout.strip() or "main"
    c = _git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}", timeout=20)
    if c.returncode != 0:
        return UpdateState(False, message="Could not compare with origin: " + c.stderr.strip()[-160:])
    ahead, behind = (int(x) for x in c.stdout.split())
    local = _git("log", "-1", "--format=%h %s", timeout=20).stdout.strip()[:70]
    remote = _git("log", "-1", "--format=%h %s", f"origin/{branch}", timeout=20).stdout.strip()[:70]
    msg = f"{behind} update(s) available" if behind else "up to date"
    return UpdateState(True, behind, ahead, local, remote, msg)


def _req_hash() -> str:
    h = hashlib.sha256()
    for name in REQ_FILES:
        p = ROOT / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def update(log: Log) -> bool:
    if not is_checkout():
        log("Not a git checkout; nothing to update.")
        return False
    was_running = teacher_running()
    if was_running:
        log("Stopping the stream for the update...")
        stop_stream()
    before = _req_hash()
    dirty = _git("status", "--porcelain", "--untracked-files=no", timeout=30).stdout.strip()
    stashed = False
    if dirty:
        log("You edited files in the app folder; keeping those edits aside while updating:")
        for line in dirty.splitlines()[:10]:
            log("   " + line)
        s = _git("stash", "push", "-m", "launcher-autostash", timeout=60)
        stashed = s.returncode == 0 and "No local changes" not in s.stdout
    code = stream_cmd(["git", "pull", "--ff-only", "origin"], log)
    if code != 0:
        log("Pull failed (see above). Nothing was changed.")
        if stashed:
            _git("stash", "pop", timeout=60)
        return False
    if stashed:
        p = _git("stash", "pop", timeout=60)
        if p.returncode == 0:
            log("Your edits were restored on top of the update.")
        else:
            log("Your edits conflict with the update; they are kept in `git stash` (git stash list) and the update version is active.")
    if _req_hash() != before:
        log("Package list changed: installing...")
        stream_cmd([str(VENV_PY), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], log)
        gpu_req = ROOT / "requirements-gpu.txt"
        try:
            has_torch = run([str(VENV_PY), "-c", "import torch"], timeout=60).returncode == 0
        except Exception:  # noqa: BLE001
            has_torch = False
        if has_torch and gpu_req.exists():
            stream_cmd([str(VENV_PY), "-m", "pip", "install", "-r", str(gpu_req)], log)
    log("Updated to: " + current_version())
    if was_running:
        log("Restarting the stream...")
        start_stream()
    return True
