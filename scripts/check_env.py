"""Verify the machine is ready: GPU, Kokoro, audio device, API credentials, chart library.

    .venv\\Scripts\\python scripts\\check_env.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

ok_all = True


def check(name: str, fn):
    global ok_all
    try:
        detail = fn()
        print(f"[ OK ] {name}: {detail}")
    except Exception as exc:  # noqa: BLE001
        ok_all = False
        print(f"[FAIL] {name}: {exc}")


def gpu():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(f"CUDA not available (torch {torch.__version__}); install the cu128 wheel")
    return f"{torch.cuda.get_device_name(0)}, torch {torch.__version__}"


def kokoro_tts():
    from app.voice.kokoro_tts import Speaker

    sp = Speaker(device="")  # device="" means default output, we only synthesize here
    t0 = time.perf_counter()
    audio = sp.synth("Welcome to the chart room. Let's look at Bitcoin.")
    dt = (time.perf_counter() - t0) * 1000
    if audio.size < 24000:
        raise RuntimeError("synthesized audio is suspiciously short")
    return f"{audio.size / 24000:.1f}s of audio in {dt:.0f} ms"


def audio_device():
    from app.voice.kokoro_tts import find_output_device
    import sounddevice as sd

    want = os.getenv("AUDIO_DEVICE", "CABLE Input")
    idx = find_output_device(want)
    if idx is None:
        raise RuntimeError(f"no output device containing {want!r}. Devices:\n{sd.query_devices()}")
    return f"[{idx}] {sd.query_devices(idx)['name']}"


def anthropic_auth():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing: copy .env.example to .env and fill it in")
    import anthropic

    client = anthropic.Anthropic()
    models = client.models.list(limit=5)
    return f"key works, {len(models.data)}+ models visible"


def tiktok_handle():
    h = os.getenv("TIKTOK_UNIQUE_ID")
    if not h:
        raise RuntimeError("TIKTOK_UNIQUE_ID missing in .env (needed to read LIVE chat)")
    return f"@{h.lstrip('@')}"


def chart_lib():
    p = ROOT / "app" / "stage" / "static" / "vendor" / "lightweight-charts.standalone.production.js"
    if not p.exists():
        raise RuntimeError("vendor/lightweight-charts.standalone.production.js missing")
    return f"{p.stat().st_size // 1024} KB"


def market_data():
    import httpx

    r = httpx.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "1h", "limit": 2}, timeout=10)
    r.raise_for_status()
    return f"Binance reachable, last close {float(r.json()[-1][4]):.0f}"


if __name__ == "__main__":
    check("GPU / torch", gpu)
    check("Kokoro TTS", kokoro_tts)
    check("Audio device", audio_device)
    check("Chart library", chart_lib)
    check("Binance data", market_data)
    check("Anthropic API", anthropic_auth)
    check("TikTok handle", tiktok_handle)
    print("\nALL GOOD" if ok_all else "\nSome checks failed (see above)")
    sys.exit(0 if ok_all else 1)
