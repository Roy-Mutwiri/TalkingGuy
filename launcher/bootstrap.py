"""TalkingGuy.exe: the one file a new PC needs.

Standard library only (tkinter, urllib, zipfile, subprocess); built with PyInstaller by installer/build_exe.ps1 and by
the GitHub Actions workflow. On every start it:

  1. makes sure Git and Python 3.12 exist (portable copies under %LOCALAPPDATA%\\TalkingGuy\\tools if the PC has none),
  2. clones the repo into %LOCALAPPDATA%\\TalkingGuy\\app (or fast-forwards it if it is already there),
  3. creates the virtual environment and installs requirements.txt (first run only),
  4. starts the launcher window from the checkout:  .venv\\Scripts\\pythonw.exe -m launcher

Because all the real code lives in the git checkout, the exe never needs to be reinstalled: the launcher's
"Update now" button pulls the latest commit and the next start runs it. Run from inside a source checkout
(python launcher/bootstrap.py) it uses that checkout instead of cloning.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.request
import zipfile
from pathlib import Path

REPO_URL = "https://github.com/Roy-Mutwiri/TalkingGuy.git"
BRANCH = "main"
PY_VERSION = "3.12.10"
PY_INSTALLER = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-amd64.exe"
MINGIT_ZIP = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/MinGit-2.47.1.2-64-bit.zip"

BASE = Path(os.getenv("TTG_HOME") or (Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "TalkingGuy"))
APP = BASE / "app"
TOOLS = BASE / "tools"
CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- tiny UI
class Window:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import scrolledtext, ttk

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("Talking Trading Guy - setup")
        self.root.geometry("720x420")
        ttk.Label(self.root, text="Talking Trading Guy", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
        self.status = ttk.Label(self.root, text="Preparing...", font=("Segoe UI", 10))
        self.status.pack(anchor="w", padx=14, pady=(2, 6))
        self.bar = ttk.Progressbar(self.root, mode="indeterminate")
        self.bar.pack(fill="x", padx=14)
        self.bar.start(12)
        self.text = scrolledtext.ScrolledText(self.root, height=14, font=("Consolas", 9), state="disabled")
        self.text.pack(fill="both", expand=True, padx=14, pady=10)
        self.closing = False
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        self.closing = True
        self.root.destroy()

    def log(self, line: str) -> None:
        def _do():
            self.text.configure(state="normal")
            self.text.insert("end", line + "\n")
            self.text.see("end")
            self.text.configure(state="disabled")
        self.root.after(0, _do)

    def set_status(self, s: str) -> None:
        self.root.after(0, lambda: self.status.configure(text=s))

    def done(self, ok: bool, msg: str) -> None:
        def _do():
            self.bar.stop()
            self.status.configure(text=msg)
            if ok:
                self.root.after(1200, self._close)
            else:
                from tkinter import ttk
                ttk.Button(self.root, text="Open log folder", command=lambda: os.startfile(str(BASE))).pack(pady=(0, 10))  # type: ignore[attr-defined]
        self.root.after(0, _do)


# ---------------------------------------------------------------- helpers
def download(url: str, dest: Path, log, label: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "TalkingGuy-setup"})
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, -1
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and (got * 20 // total) != last:
                last = got * 20 // total
                log(f"{label}: {got * 100 // total}%  ({got / 1e6:.0f} / {total / 1e6:.0f} MB)")
    tmp.replace(dest)
    return dest


def run_stream(cmd: list[str], log, cwd: Path | None = None, env: dict | None = None) -> int:
    log("> " + " ".join(cmd))
    p = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
    assert p.stdout is not None
    for line in p.stdout:
        if line.strip():
            log(line.rstrip())
    return p.wait()


def run_quiet(cmd: list[str], env: dict | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
                          creationflags=CREATE_NO_WINDOW)


def child_env() -> dict:
    env = os.environ.copy()
    extra = [TOOLS / "git" / "cmd", TOOLS / "ffmpeg" / "bin", TOOLS / "python312", TOOLS / "python312" / "Scripts"]
    env["PATH"] = os.pathsep.join([str(p) for p in extra if p.exists()] + [env.get("PATH", "")])
    env["TTG_TOOLS"] = str(TOOLS)
    env["TTG_HOME"] = str(BASE)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ---------------------------------------------------------------- steps
def ensure_git(log) -> str:
    g = shutil.which("git", path=child_env()["PATH"])
    if g:
        log(f"Git: {g}")
        return g
    log("Git: not found, fetching a portable copy (about 40 MB)...")
    z = download(MINGIT_ZIP, TOOLS / "downloads" / "mingit.zip", log, "Git")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(TOOLS / "git")
    g = str(TOOLS / "git" / "cmd" / "git.exe")
    if not Path(g).exists():
        raise RuntimeError("portable Git did not unpack")
    log("Git: ready (portable).")
    return g


def _py_version_ok(exe: str) -> bool:
    try:
        r = run_quiet([exe, "-c", "import sys; print(sys.version_info[:2] == (3, 12))"], env=child_env(), timeout=20)
        return r.returncode == 0 and "True" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def ensure_python(log) -> str:
    cands = [str(TOOLS / "python312" / "python.exe")]
    env = child_env()
    try:
        r = run_quiet(["py", "-3.12", "-c", "import sys; print(sys.executable)"], env=env, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            cands.append(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        pass
    for name in ("python3.12", "python"):
        w = shutil.which(name, path=env["PATH"])
        if w:
            cands.append(w)
    for c in cands:
        if Path(c).exists() and _py_version_ok(c):
            log(f"Python 3.12: {c}")
            return c
    log("Python 3.12: not found, installing a private copy (about 25 MB download, per-user, no admin)...")
    exe = download(PY_INSTALLER, TOOLS / "downloads" / f"python-{PY_VERSION}-amd64.exe", log, "Python")
    target = TOOLS / "python312"
    code = subprocess.call([str(exe), "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0",
                            "Include_doc=0", "SimpleInstall=1", f"TargetDir={target}"], creationflags=CREATE_NO_WINDOW)
    py = target / "python.exe"
    if code != 0 or not py.exists():
        raise RuntimeError(f"Python installer exit code {code}")
    log("Python 3.12: installed.")
    return str(py)


def ensure_checkout(git: str, log) -> Path:
    env = child_env()
    if (APP / ".git").exists():
        log("App: already installed, fetching the latest version...")
        code = run_stream([git, "-C", str(APP), "pull", "--ff-only", "origin", BRANCH], log, env=env)
        if code != 0:
            log("App: could not fast-forward (local edits?). Keeping the current version; use 'Update now' in the launcher.")
        return APP
    if APP.exists() and any(APP.iterdir()):
        raise RuntimeError(f"{APP} exists but is not a git checkout. Move it away and run again.")
    APP.parent.mkdir(parents=True, exist_ok=True)
    log(f"App: downloading from {REPO_URL} ...")
    code = run_stream([git, "clone", "--branch", BRANCH, "--depth", "50", REPO_URL, str(APP)], log, env=env)
    if code != 0:
        raise RuntimeError("git clone failed")
    return APP


def ensure_venv(python: str, app: Path, log) -> Path:
    venv_py = app / ".venv" / "Scripts" / "python.exe"
    env = child_env()
    if not venv_py.exists():
        log("Environment: creating .venv ...")
        code = run_stream([python, "-m", "venv", str(app / ".venv")], log, env=env)
        if code != 0 or not venv_py.exists():
            raise RuntimeError("could not create the virtual environment")
        run_stream([str(venv_py), "-m", "pip", "install", "--upgrade", "pip"], log, env=env)
    marker = app / ".venv" / "requirements.installed"
    req = app / "requirements.txt"
    if not marker.exists() or marker.read_bytes() != req.read_bytes():
        log("Environment: installing packages (first run: a few hundred MB)...")
        code = run_stream([str(venv_py), "-m", "pip", "install", "-r", str(req)], log, cwd=app, env=env)
        if code != 0:
            raise RuntimeError("pip install failed")
        marker.write_bytes(req.read_bytes())
    if not (app / ".env").exists() and (app / ".env.example").exists():
        shutil.copy(app / ".env.example", app / ".env")
    return venv_py


def launch(venv_py: Path, app: Path, log) -> None:
    pyw = venv_py.with_name("pythonw.exe")
    log("Starting the launcher...")
    subprocess.Popen([str(pyw if pyw.exists() else venv_py), "-m", "launcher"], cwd=str(app), env=child_env(),
                     creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def source_checkout() -> Path | None:
    """Running from a source checkout (python launcher/bootstrap.py): use it instead of cloning."""
    if getattr(sys, "frozen", False):
        return None
    here = Path(__file__).resolve().parent.parent
    return here if (here / "launcher" / "gui.py").exists() and (here / "app").exists() else None


def main() -> None:
    win = Window()
    BASE.mkdir(parents=True, exist_ok=True)
    logfile = BASE / "setup.log"

    def log(line: str) -> None:
        win.log(line)
        try:
            with logfile.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def work() -> None:
        try:
            src = source_checkout()
            win.set_status("Checking Git and Python...")
            git = ensure_git(log)
            python = ensure_python(log)
            win.set_status("Getting the app...")
            app = src or ensure_checkout(git, log)
            win.set_status("Preparing the Python environment...")
            venv_py = ensure_venv(python, app, log)
            win.set_status("Done.")
            launch(venv_py, app, log)
            win.done(True, "Ready. The launcher window is opening.")
        except Exception as exc:  # noqa: BLE001
            log("ERROR: " + str(exc))
            log(traceback.format_exc())
            win.done(False, f"Setup failed: {exc}. Log: {logfile}")

    threading.Thread(target=work, daemon=True).start()
    win.root.mainloop()


if __name__ == "__main__":
    main()
