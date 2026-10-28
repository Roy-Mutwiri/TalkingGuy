"""Speak a few sentences through an audio device and print timing + mouth levels.

    .venv\\Scripts\\python scripts\\test_voice.py --device Speakers                       # hear it locally (engine from .env, default edge)
    .venv\\Scripts\\python scripts\\test_voice.py --engine kokoro --device Speakers
    .venv\\Scripts\\python scripts\\test_voice.py --engine edge --voice en-GB-RyanNeural --device Speakers
    .venv\\Scripts\\python scripts\\test_voice.py --device list
    .venv\\Scripts\\python scripts\\test_voice.py --wav sample.wav
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

TEXT = ("Welcome to the chart room. Today we look at the bullish engulfing candle. "
        "It only matters where buyers had a reason to show up. Let's see one on Bitcoin.")


async def main(engine: str | None, device: str | None, voice: str | None, wav: str | None) -> None:
    from app.voice import make_speaker
    from app.voice.kokoro_tts import list_devices

    if device == "list":
        print(list_devices())
        return
    sp = make_speaker(engine, voice=voice, device=device)
    print("engine:", type(sp).__name__, "voice:", sp.voice)
    if wav:
        import soundfile as sf

        audio = sp.synth(TEXT)
        sf.write(wav, audio, sp.out_rate)
        print(f"wrote {wav} ({audio.size / sp.out_rate:.1f}s)")
        return
    t0 = time.perf_counter()
    first = None
    levels = 0
    async for ev in sp.speak(TEXT):
        if ev["event"] == "sentence":
            if first is None:
                first = (time.perf_counter() - t0) * 1000
                print(f"first audio after {first:.0f} ms")
            print(f"  sentence ({ev['duration_ms']} ms): {ev['text']}")
        elif ev["event"] == "level":
            levels += 1
        elif ev["event"] == "error":
            print("ERROR:", ev["error"])
    print(f"done in {(time.perf_counter() - t0):.1f}s, {levels} level events, underruns={getattr(sp._ring, 'underruns', 0)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=None, help="edge or kokoro (default: TTS_ENGINE in .env, else edge)")
    ap.add_argument("--device", default=None, help='substring of the output device, or "list"')
    ap.add_argument("--voice", default=None)
    ap.add_argument("--wav", default=None, help="write to a wav file instead of playing")
    a = ap.parse_args()
    asyncio.run(main(a.engine, a.device, a.voice, a.wav))
