"""Measure the voice chain like an audio engineer, and render A/B files to listen to.

    python scripts/voice_check.py

Writes data_cache/voice_samples/chain_raw.wav (Edge voice untouched), chain_old.wav (previous
humanizer) and chain_new.wav (broadcast chain), and prints for each: RMS, peak, crest factor,
noise floor in the gaps, spectral balance (low / mid / presence / air), sibilance ratio, clipping.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEXT = [
    "Okay chat, here we go. Gold just tapped the level for the second time, and this is the part that matters.",
    "Sam, you spotted it. The second attempt closed back inside the range, so the breakout failed.",
    "Six sessions, sixteen seconds, sixty-six sellers. Watch the structure, not the story.",
    "No rush, Nia. Let's make this easier with one example on the live chart.",
]


def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-9))


def band_rms(x: np.ndarray, rate: int, lo: float, hi: float) -> float:
    spec = np.fft.rfft(x * np.hanning(x.size))
    f = np.fft.rfftfreq(x.size, 1 / rate)
    m = (f >= lo) & (f < hi)
    return float(np.sqrt(np.mean(np.abs(spec[m]) ** 2))) if m.any() else 0.0


def metrics(name: str, x: np.ndarray, rate: int) -> dict:
    a = np.abs(x)
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(a.max())
    # gaps = quietest 10 % of 20 ms frames
    fr = int(rate * 0.02)
    frames = x[: x.size // fr * fr].reshape(-1, fr)
    frms = np.sqrt(np.mean(frames ** 2, axis=1))
    floor = float(np.percentile(frms, 10))
    loudmask = frms > np.percentile(frms, 60)
    loud = frames[loudmask].ravel()
    loud_rms = float(np.sqrt(np.mean(loud ** 2)))
    consistency = float(np.std(20 * np.log10(np.maximum(frms[loudmask], 1e-9))))
    low, mid, pres, air, sib = (band_rms(loud, rate, *b) for b in [(80, 300), (300, 2000), (2000, 5000), (8000, 12000), (5000, 9000)])
    clip = int(np.sum(a >= 0.985))
    out = {"name": name, "rms_dbfs": db(loud_rms), "peak_dbfs": db(peak), "crest_db": db(peak) - db(loud_rms), "floor_dbfs": db(floor), "consistency_db": consistency,
           "low_vs_mid_db": db(low) - db(mid), "presence_vs_mid_db": db(pres) - db(mid), "air_vs_mid_db": db(air) - db(mid),
           "sibilance_vs_mid_db": db(sib) - db(mid), "clipped_samples": clip}
    print(f"{name:10} loudRMS {out['rms_dbfs']:6.1f} dBFS  peak {out['peak_dbfs']:6.1f}  crest {out['crest_db']:4.1f} dB  steadiness ±{consistency:3.1f} dB  floor {out['floor_dbfs']:6.1f} dBFS  "
          f"low {out['low_vs_mid_db']:+5.1f}  presence {out['presence_vs_mid_db']:+5.1f}  air {out['air_vs_mid_db']:+5.1f}  sib {out['sibilance_vs_mid_db']:+5.1f}  clipped {clip}")
    return out


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    from app.voice import humanize_audio as new
    from app.voice import humanize_audio_legacy as old
    from app.voice.edge_voice import EdgeSpeaker

    out = Path("data_cache/voice_samples")
    out.mkdir(parents=True, exist_ok=True)
    sp = EdgeSpeaker(voice=os.getenv("TTS_VOICE", "en-US-AndrewMultilingualNeural"))
    sp.mood = "show"
    rate = sp.out_rate
    raws = [await sp._fetch(t) for t in TEXT]
    gap = np.zeros(int(rate * 0.25), dtype=np.float32)
    raw = np.concatenate([np.concatenate([r, gap]) for r in raws])
    chain_old = np.concatenate([old.humanize_sentence(r, rate, first=(i == 0), long_prev=False, mood="show") for i, r in enumerate(raws)])
    chain_new = np.concatenate([new.humanize_sentence(r, rate, first=(i == 0), long_prev=False, mood="show") for i, r in enumerate(raws)])
    for name, x in [("raw", raw), ("old", chain_old), ("new", chain_new)]:
        sf.write(out / f"chain_{name}.wav", x, rate)
        metrics(name, x, rate)
    print(f"\nfiles in {out}: chain_raw.wav, chain_old.wav, chain_new.wav  ({rate} Hz)")


if __name__ == "__main__":
    asyncio.run(main())
