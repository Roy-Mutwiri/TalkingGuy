"""Recorded non-verbal sounds of the host: laughs, chuckle, sighs, groan, breaths and the little murmurs.

Cut from the host's own recording into app/voice/ref/sfx/*.wav (see index.json there). When a sample exists it is
used instead of a synthetic noise or a synthesised word:
  * a [laugh] / [chuckle] / [sigh] / [groan] tag at the start or end of a sentence plays the real sound and the
    tag is removed before synthesis (tags in the middle of a sentence are still performed by the voice engine)
  * breaths and inhales in the humanizer come from the recording
  * the murmurs while drawing ("mm", "okay", "right, so") are the host's own, not synthesised

Samples are resampled to the output rate once and level-matched to the broadcast chain so they sit where the
voice sits. Missing samples fall back to the old behaviour; the stream never depends on them.
"""
from __future__ import annotations

import logging
import random
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger("voice")
SFX_DIR = Path(__file__).resolve().parent / "ref" / "sfx"
_TAG_EDGE = re.compile(r"^\s*\[\s*([a-zA-Z ]{3,14})\s*\]\s*|\s*\[\s*([a-zA-Z ]{3,14})\s*\]\s*$")

# tag (engine vocabulary) -> sample name prefixes that can stand in for it
FAMILIES: dict[str, list[str]] = {
    "laugh": ["laugh_small", "laugh_warm"],            # the big laughs stay out of automatic use: they only sound right when earned
    "chuckle": ["chuckle"],
    "sigh": ["sigh_short", "sigh_long"],
    "groan": ["groan"],
    "breath": ["breathing"],                           # a short slice of normal breathing, never the deliberate inhale
    "inhale": ["breath_slow"],
    "murmur": ["murmur_hmm", "murmur_mm_hm", "murmur_okay", "murmur_right_so", "murmur_yeah", "murmur_there", "murmur_let_me_see"],
}
# target RMS (dBFS) per family so a laugh sits at speech level and a breath stays under it
# a real breath sits 25-30 dB under the voice (speech is normalised to -17 dBFS RMS); laughs a little under speech level
LEVEL_DB = {"laugh": -23.0, "chuckle": -26.0, "sigh": -30.0, "groan": -27.0, "breath": -45.0, "inhale": -40.0, "murmur": -26.0}
SLICE_S = {"breath": (0.25, 0.45), "inhale": (0.45, 0.7)}     # families served as a random short slice of the sample


def available() -> bool:
    return SFX_DIR.exists() and any(SFX_DIR.glob("*.wav"))


@lru_cache(maxsize=64)
def _load(name: str, rate: int) -> np.ndarray | None:
    p = SFX_DIR / f"{name}.wav"
    if not p.exists():
        return None
    try:
        import soundfile as sf
        from scipy.signal import resample_poly

        x, sr = sf.read(p, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr != rate:
            from math import gcd

            g = gcd(rate, sr)
            x = resample_poly(x, rate // g, sr // g).astype(np.float32)
        return np.asarray(x, dtype=np.float32)
    except Exception as exc:  # noqa: BLE001
        log.warning("sfx %s: %s", name, exc)
        return None


def get(family: str, rate: int, rng: random.Random | np.random.Generator | None = None) -> np.ndarray | None:
    """A level-matched sample for the family, or None when the recording does not have one."""
    names = FAMILIES.get(family, [])
    if not names:
        return None
    order = list(names)
    r = rng if isinstance(rng, random.Random) else random
    (r.shuffle(order) if isinstance(r, random.Random) else random.shuffle(order))
    for name in order:
        x = _load(name, rate)
        if x is None or x.size < rate // 20:
            continue
        if family in SLICE_S:
            lo, hi = SLICE_S[family]
            want = int(rate * (lo + (hi - lo) * (r.random() if isinstance(r, random.Random) else random.random())))
            if x.size > want + rate // 10:
                start = (r.randint if isinstance(r, random.Random) else random.randint)(0, x.size - want - 1)
                x = x[start:start + want].copy()
            n = max(8, int(rate * 0.04))
            ramp = np.linspace(0, 1, n, dtype=np.float32)
            x[:n] *= ramp
            x[-n:] *= ramp[::-1]
        rms = float(np.sqrt(np.mean(x ** 2))) or 1e-6
        g = 10 ** (LEVEL_DB.get(family, -24.0) / 20) / rms
        y = np.clip(x * min(g, 10 ** (24 / 20)), -0.95, 0.95).astype(np.float32)
        return y
    return None


def split_edge_tags(sentence: str) -> tuple[list[str], str, list[str]]:
    """([leading families], stripped sentence, [trailing families]) for tags we have samples for.
    Tags without a sample are left in place for the voice engine."""
    from .tags import CANON

    lead: list[str] = []
    tail: list[str] = []
    s = sentence
    changed = True
    while changed:
        changed = False
        m = re.match(r"^\s*\[\s*([a-zA-Z ]{3,14})\s*\]\s*", s)
        if m:
            fam = CANON.get(" ".join(m.group(1).lower().split()))
            if fam in FAMILIES and _load(FAMILIES[fam][0], 24000) is not None:
                lead.append(fam)
                s = s[m.end():]
                changed = True
                continue
        m = re.search(r"\s*\[\s*([a-zA-Z ]{3,14})\s*\]\s*$", s)
        if m:
            fam = CANON.get(" ".join(m.group(1).lower().split()))
            if fam in FAMILIES and _load(FAMILIES[fam][0], 24000) is not None:
                tail.append(fam)
                s = s[:m.start()]
                changed = True
    return lead, s.strip(), tail


def gap(rate: int, seconds: float) -> np.ndarray:
    return np.zeros(int(rate * seconds), dtype=np.float32)


def join(parts: list[np.ndarray], rate: int, xfade_s: float = 0.08) -> np.ndarray:
    """Concatenate with short crossfades so a recorded sound runs into the voice instead of sitting on top of it."""
    parts = [np.asarray(p, dtype=np.float32) for p in parts if p is not None and p.size]
    if not parts:
        return np.zeros(0, dtype=np.float32)
    out = parts[0].copy()
    n = int(rate * xfade_s)
    for p in parts[1:]:
        k = min(n, out.size, p.size)
        if k > 8:
            ramp = np.linspace(0, 1, k, dtype=np.float32)
            out[-k:] = out[-k:] * (1 - ramp) + p[:k] * ramp
            out = np.concatenate([out, p[k:]])
        else:
            out = np.concatenate([out, p])
    return out.astype(np.float32)
