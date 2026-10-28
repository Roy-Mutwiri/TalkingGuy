"""One-click setup steps the launcher runs on a fresh PC: dependencies, tools, voice, Claude access.

Each step takes a `log(line)` callback and returns True on success. They are idempotent: running a step
that is already done just reports it.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

from .common import (CREATE_NO_WINDOW, ROOT, TOOLS, VENV_PY, Log, claude_cli, download, gpu_name, gpu_voice_installed, has_ffmpeg,
                     has_vbcable, has_webview2, read_env, run, stream_cmd, unzip, write_env)

FFMPEG_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
VBCABLE_ZIP = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
WEBVIEW2_BOOTSTRAPPER = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"


# ---------------------------------------------------------------- python packages
def install_core(log: Log) -> bool:
    log("Installing the core Python packages (requirements.txt)...")
    code = stream_cmd([str(VENV_PY), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], log)
    log("Core packages ready." if code == 0 else f"pip failed with code {code}.")
    return code == 0


def install_gpu_voice(log: Log) -> bool:
    name = gpu_name()
    if not name:
        log("No NVIDIA GPU found (nvidia-smi missing). The local AI voice needs one; the stream uses the online voice instead.")
        return False
    if gpu_voice_installed():
        log(f"Local AI voice already installed on {name}.")
        return True
    log(f"GPU: {name}. Installing torch with CUDA 12.8 (about 3 GB, this takes a while on a slow line)...")
    code = stream_cmd([str(VENV_PY), "-m", "pip", "install", "torch==2.11.0", "torchaudio==2.11.0", "--index-url", TORCH_INDEX], log)
    if code != 0:
        log("torch install failed.")
        return False
    code = stream_cmd([str(VENV_PY), "-m", "pip", "install", "-r", str(ROOT / "requirements-gpu.txt")], log)
    ok = code == 0 and gpu_voice_installed()
    if ok:
        write_env({"TTS_ENGINE": "chatterbox"})
        log("Local AI voice installed; TTS_ENGINE=chatterbox. The voice model downloads itself on the first start.")
    else:
        log("Local AI voice did not come up; staying on the online voice.")
    return ok


# ---------------------------------------------------------------- tools
def install_ffmpeg(log: Log) -> bool:
    if has_ffmpeg():
        log("ffmpeg: found.")
        return True
    dest = TOOLS / "ffmpeg"
    log("ffmpeg: downloading a portable build (about 90 MB)...")
    z = download(FFMPEG_ZIP, TOOLS / "downloads" / "ffmpeg.zip", log, "ffmpeg")
    unzip(z, dest, strip_top=True)
    ok = (dest / "bin" / "ffmpeg.exe").exists()
    log("ffmpeg: installed to " + str(dest) if ok else "ffmpeg: unpack failed")
    return ok


def install_webview2(log: Log) -> bool:
    if has_webview2():
        log("WebView2 runtime: present.")
        return True
    log("WebView2 runtime: downloading Microsoft's installer...")
    exe = download(WEBVIEW2_BOOTSTRAPPER, TOOLS / "downloads" / "MicrosoftEdgeWebview2Setup.exe", log, "WebView2")
    code = subprocess.call([str(exe), "/silent", "/install"], creationflags=CREATE_NO_WINDOW)
    ok = has_webview2()
    log("WebView2 runtime: installed." if ok else f"WebView2 installer exit code {code}; if the stage window stays blank, install it from Microsoft.")
    return ok


def install_vbcable(log: Log) -> bool:
    """VB-Audio Virtual Cable: the pipe that carries Theo's voice into LIVE Studio as a microphone. Driver install needs admin."""
    if has_vbcable():
        log("VB-Cable: installed (CABLE Input found).")
        return True
    log("VB-Cable: downloading the driver pack from vb-audio.com...")
    z = download(VBCABLE_ZIP, TOOLS / "downloads" / "vbcable.zip", log, "VB-Cable")
    dest = TOOLS / "vbcable"
    unzip(z, dest)
    setup = next(iter(dest.glob("VBCABLE_Setup_x64.exe")), None) or next(iter(dest.rglob("VBCABLE_Setup_x64.exe")), None)
    if not setup:
        log("VB-Cable: setup file not found in the pack.")
        return False
    log("VB-Cable: Windows will ask for admin rights. In the installer window press 'Install Driver', then reboot once.")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(setup), None, str(setup.parent), 1)
    if rc <= 32:
        log("VB-Cable: the admin prompt was declined or failed.")
        return False
    return True


# ---------------------------------------------------------------- Claude access
def set_api_key(key: str, log: Log) -> bool:
    key = key.strip()
    if not key.startswith("sk-ant-"):
        log("That does not look like an Anthropic API key (they start with sk-ant-).")
        return False
    write_env({"ANTHROPIC_API_KEY": key, "BRAIN_BACKEND": "api"})
    log("Testing the key...")
    code = r"""
import os, sys
from dotenv import load_dotenv; load_dotenv(r'%s')
import anthropic
c = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
m = c.models.list(limit=1)
print('ok', m.data[0].id if m.data else '')
""" % (ROOT / ".env")
    r = run([str(VENV_PY), "-c", code], timeout=60)
    ok = r.returncode == 0 and "ok" in r.stdout
    log("API key works. Lessons and chat answers will use it." if ok else "Key test failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:200])
    return ok


def claude_login(log: Log) -> bool:
    """Open the Claude sign-in (claude.ai account) in a console window. For your own machines; see README."""
    cli = claude_cli()
    if not cli:
        log("Claude CLI not found in the environment (install the core packages first).")
        return False
    write_env({"BRAIN_BACKEND": "claude_code"})
    log("A console window opens: follow the sign-in in your browser, then come back here and press 'Check sign-in'.")
    subprocess.Popen(["cmd", "/c", "start", "Claude sign-in", str(cli), "auth", "login"], cwd=str(ROOT), creationflags=CREATE_NO_WINDOW)
    return True


def claude_status(log: Log) -> bool:
    cli = claude_cli()
    if not cli:
        log("Claude CLI not found.")
        return False
    r = run([str(cli), "auth", "status"], timeout=30)
    out = (r.stdout + r.stderr).strip()
    ok = r.returncode == 0 and ("logged in" in out.lower() or "authenticated" in out.lower() or "email" in out.lower()) and "not logged" not in out.lower()
    log(("Signed in: " if ok else "Not signed in: ") + out.replace("\n", " | ")[:300])
    return ok


def brain_summary() -> str:
    env = read_env()
    if env.get("BRAIN_BACKEND", "api") == "claude_code":
        return "Claude sign-in (claude.ai account on this PC)"
    return "API key set" if env.get("ANTHROPIC_API_KEY") else "no Claude access yet (offline template lessons)"


# ---------------------------------------------------------------- full check
def check_environment(log: Log) -> bool:
    log("Running scripts/check_env.py ...")
    code = stream_cmd([str(VENV_PY), str(ROOT / "scripts" / "check_env.py")], log)
    return code == 0


def first_run_setup(log: Log, want_gpu_voice: bool) -> None:
    """Everything that needs no questions: packages, ffmpeg, WebView2, optional GPU voice. Returns when done."""
    t0 = time.time()
    install_core(log)
    install_ffmpeg(log)
    install_webview2(log)
    if want_gpu_voice:
        install_gpu_voice(log)
    else:
        if not read_env().get("TTS_ENGINE") or read_env().get("TTS_ENGINE") == "chatterbox" and not gpu_voice_installed():
            write_env({"TTS_ENGINE": "edge"})
            log("Voice: online voice (Edge). You can install the local AI voice later from the Setup tab.")
    log(f"Setup finished in {time.time() - t0:.0f}s.")
