"""Fetch real human reference voices from a public, openly licensed corpus for the expressive engine.

    python scripts/fetch_public_voices.py             # 3 male candidates -> app/voice/ref/libritts_<speaker>.wav

Source: LibriTTS-R (LibriVox public-domain audiobook readings, released under CC BY 4.0). One parquet
shard of dev.clean is downloaded, clips are grouped by speaker, speakers are ranked for a lively male
voice (median pitch 85-165 Hz, loud, fast, clean), and the best 8-14 s clip per speaker is saved with
an attribution file. Then Haddan's test line is rendered with each candidate so you can listen and pick.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REF = ROOT / "app" / "voice" / "ref"
REPO, SHARD = "mythicinfinity/libritts_r", "data/dev.clean/dev.clean-00000-of-00004.parquet"


def pitch_hz(x: np.ndarray, sr: int) -> float:
    """Median fundamental via autocorrelation on voiced 40 ms frames (good enough to tell male from female)."""
    fr = int(sr * 0.04)
    f0s = []
    for i in range(0, len(x) - fr, fr):
        seg = x[i:i + fr]
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, "full")[fr - 1:]
        lo, hi = int(sr / 300), int(sr / 70)
        if hi >= len(ac):
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            f0s.append(sr / k)
    return float(np.median(f0s)) if f0s else 0.0


def main() -> None:
    REF.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(REPO, SHARD, repo_type="dataset")
    t = pq.read_table(path)
    cols = t.column_names
    print("columns:", cols, "| rows:", t.num_rows)
    audio_col = "audio" if "audio" in cols else next(c for c in cols if "audio" in c.lower())
    spk_col = next((c for c in cols if c in ("speaker_id", "speaker")), None)
    txt_col = next((c for c in cols if c in ("text_normalized", "text_original", "text")), None)
    by_spk: dict[str, list[dict]] = {}
    for row in t.to_pylist():
        a = row[audio_col]
        raw = a.get("bytes") if isinstance(a, dict) else None
        if not raw:
            continue
        x, sr = sf.read(io.BytesIO(raw), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        dur = len(x) / sr
        if not (8.0 <= dur <= 15.0):
            continue
        spk = str(row.get(spk_col, "?"))
        by_spk.setdefault(spk, []).append({"x": x, "sr": sr, "dur": dur, "text": row.get(txt_col, "")})
        if sum(len(v) for v in by_spk.values()) > 400:
            break
    ranked = []
    for spk, clips in by_spk.items():
        for c in clips[:3]:
            f0 = pitch_hz(c["x"], c["sr"])
            if not (85 <= f0 <= 165):
                continue
            rms = float(np.sqrt(np.mean(c["x"] ** 2)))
            wps = len(str(c["text"]).split()) / c["dur"]
            score = rms * 10 + min(wps, 3.2) * 0.5 - abs(f0 - 115) / 100     # loud, brisk, clearly male
            ranked.append((score, spk, f0, wps, c))
    ranked.sort(key=lambda r: -r[0])
    chosen, seen = [], set()
    for score, spk, f0, wps, c in ranked:
        if spk in seen:
            continue
        seen.add(spk)
        out = REF / f"libritts_{spk}.wav"
        sf.write(out, c["x"], c["sr"])
        chosen.append({"file": out.name, "speaker": spk, "pitch_hz": round(f0, 1), "words_per_s": round(wps, 2), "seconds": round(c["dur"], 1),
                       "source": f"LibriTTS-R {SHARD} (LibriVox public-domain reading), CC BY 4.0", "text": str(c["text"])[:120]})
        print(f"saved {out.name}: speaker {spk}, pitch {f0:.0f} Hz, {wps:.1f} words/s, {c['dur']:.1f}s")
        if len(chosen) == 3:
            break
    (REF / "ATTRIBUTION.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    if not chosen:
        sys.exit("no suitable male clips found in this shard")

    # render Haddan's test line with each candidate
    from app.voice.chatterbox_voice import ChatterboxSpeaker

    sp = ChatterboxSpeaker(device="CABLE Input")
    sp.mood = "show"
    line = "Okay chat, here we go. [chuckle] Gold just tapped the level for the second time, and this is the part that matters. [sigh] No rush, we read it together."
    samples = ROOT / "data_cache" / "voice_samples"
    samples.mkdir(parents=True, exist_ok=True)
    for c in chosen:
        sp.voice = str(REF / c["file"])
        sp._cache.clear()
        a = sp.synth_many([line])[0]
        sf.write(samples / f"ref_{c['speaker']}.wav", a, sp.out_rate)
        print(f"rendered data_cache/voice_samples/ref_{c['speaker']}.wav")
    print("default reference ->", chosen[0]["file"])


if __name__ == "__main__":
    main()
