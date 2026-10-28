"""Broadcast voice chain: make synthesized speech sound like a person on a top-end studio microphone.

Applied per sentence after synthesis (vectorised with scipy, a few ms per sentence). The chain is the
one a streaming engineer puts after an SM7B / U87 class microphone into a clean preamp:

  1. high-pass 75 Hz (rumble/plosive floor)          5. de-esser (5-9 kHz, only when sibilance spikes)
  2. low shelf +1.5 dB @ 110 Hz (proximity warmth)    6. soft-knee compressor 3:1 @ -20 dBFS, 6 ms / 140 ms
  3. mud cut -2 dB @ 300 Hz (clarity)                 7. loudness normalisation to -19 dBFS RMS
  4. presence +3 dB @ 3.2 kHz, air +2.5 dB @ 9.5 kHz  8. look-ahead peak limiter at -1 dBFS (no clipping)

Human layer, kept subtle: an occasional quiet breath before a sentence, a varying pause, and a
near-silent studio tone (-72 dBFS, inaudible) so there is never a dead digital zero. No room noise,
no hiss: an expensive microphone in a treated room is quiet.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, lfilter

_rng = np.random.default_rng(7)
_cache: dict = {}

TARGET_RMS_DBFS = -17.0      # broadcast speech level for the loud frames (about -15 LUFS integrated)
LIMIT_DBFS = -1.0


# ------------------------------------------------------------------ filters (RBJ cookbook biquads)
def _biquad(kind: str, rate: int, f0: float, q: float = 0.707, gain_db: float = 0.0):
    key = ("bq", kind, rate, round(f0, 3), round(q, 4), round(gain_db, 3))
    if key in _cache:
        return _cache[key]
    a_lin = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / rate
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b0, b1, b2 = 1 + alpha * a_lin, -2 * cw, 1 - alpha * a_lin
        a0, a1, a2 = 1 + alpha / a_lin, -2 * cw, 1 - alpha / a_lin
    elif kind == "lowshelf":
        s = 2 * math.sqrt(a_lin) * alpha
        b0 = a_lin * ((a_lin + 1) - (a_lin - 1) * cw + s)
        b1 = 2 * a_lin * ((a_lin - 1) - (a_lin + 1) * cw)
        b2 = a_lin * ((a_lin + 1) - (a_lin - 1) * cw - s)
        a0 = (a_lin + 1) + (a_lin - 1) * cw + s
        a1 = -2 * ((a_lin - 1) + (a_lin + 1) * cw)
        a2 = (a_lin + 1) + (a_lin - 1) * cw - s
    elif kind == "highshelf":
        s = 2 * math.sqrt(a_lin) * alpha
        b0 = a_lin * ((a_lin + 1) + (a_lin - 1) * cw + s)
        b1 = -2 * a_lin * ((a_lin - 1) + (a_lin + 1) * cw)
        b2 = a_lin * ((a_lin + 1) + (a_lin - 1) * cw - s)
        a0 = (a_lin + 1) - (a_lin - 1) * cw + s
        a1 = 2 * ((a_lin - 1) - (a_lin + 1) * cw)
        a2 = (a_lin + 1) - (a_lin - 1) * cw - s
    elif kind == "highpass":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "lowpass":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bandpass":
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    else:
        raise ValueError(kind)
    coef = (np.array([b0, b1, b2]) / a0, np.array([a0, a1, a2]) / a0)
    _cache[key] = coef
    return coef


def _bq(kind: str, x: np.ndarray, rate: int, f0: float, q: float = 0.707, gain_db: float = 0.0) -> np.ndarray:
    b, a = _biquad(kind, rate, f0, q, gain_db)
    return lfilter(b, a, x).astype(np.float32)


def _coef(kind: str, rate: int, fc, order: int = 2):
    key = (kind, rate, fc if not isinstance(fc, list) else tuple(fc), order)
    if key not in _cache:
        _cache[key] = butter(order, fc, btype=kind, fs=rate)
    return _cache[key]


def _filt(kind: str, x: np.ndarray, rate: int, fc, order: int = 2) -> np.ndarray:
    b, a = _coef(kind, rate, fc, order)
    return lfilter(b, a, x).astype(np.float32)


def _env(x: np.ndarray, rate: int, attack_ms: float, release_ms: float) -> np.ndarray:
    """Peak envelope with separate attack/release time constants (sample-accurate, vectorised in chunks)."""
    a_att = math.exp(-1.0 / (rate * attack_ms / 1000.0))
    a_rel = math.exp(-1.0 / (rate * release_ms / 1000.0))
    ax = np.abs(x).astype(np.float64)
    # two one-pole followers combined: the max of a fast-attack path and a slow-release path
    # (lfilter gives us each path without a python loop)
    fast = lfilter([1 - a_att], [1, -a_att], ax)
    slow = lfilter([1 - a_rel], [1, -a_rel], ax)
    env = np.maximum(fast, slow)
    return env.astype(np.float32)


# ------------------------------------------------------------------ dynamics
def deess(x: np.ndarray, rate: int, lo: float = 5000.0, hi: float = 9000.0, share: float = 0.36, max_cut_db: float = 10.0) -> np.ndarray:
    """Turn the 5-9 kHz band down only while it stands out from the whole voice (an "s" or "sh"),
    leaving everything else untouched. Relative detection, so it works at any level."""
    if x.size < 64:
        return x
    band = _filt("band", x, rate, [lo, min(hi, rate / 2 - 100)], 2)
    env_b = _env(band, rate, 1.0, 40.0)
    env_x = _env(x, rate, 1.0, 40.0)
    excess = env_b / np.maximum(env_x * share, 1e-6)          # > 1 = sibilance dominating
    gain = np.minimum(1.0, 1.0 / np.maximum(excess, 1e-6))
    gain = np.maximum(gain, 10 ** (-max_cut_db / 20))
    return (x - band * (1.0 - gain)).astype(np.float32)


def compress(x: np.ndarray, rate: int, threshold_db: float = -27.0, ratio: float = 3.2, knee_db: float = 8.0,
             attack_ms: float = 6.0, release_ms: float = 140.0, makeup_db: float = 0.0, **_legacy) -> np.ndarray:
    """Soft-knee feed-forward compressor on a peak envelope."""
    if x.size == 0:
        return x
    env = _env(x, rate, attack_ms, release_ms)
    lvl = 20 * np.log10(np.maximum(env, 1e-6))
    over = lvl - threshold_db
    half = knee_db / 2
    gr = np.zeros_like(lvl)
    inknee = (over > -half) & (over < half)
    gr[inknee] = (1 / ratio - 1) * (over[inknee] + half) ** 2 / (2 * knee_db)
    above = over >= half
    gr[above] = (1 / ratio - 1) * over[above]
    gain = 10 ** ((gr + makeup_db) / 20)
    return (x * gain).astype(np.float32)


def normalize(x: np.ndarray, target_dbfs: float = TARGET_RMS_DBFS) -> np.ndarray:
    """Bring the sentence to a consistent broadcast level (RMS over the louder half of the signal)."""
    if x.size == 0:
        return x
    a = np.abs(x)
    gate = a > max(1e-4, np.percentile(a, 50))
    rms = float(np.sqrt(np.mean(x[gate] ** 2))) if gate.any() else float(np.sqrt(np.mean(x ** 2)))
    if rms < 1e-6:
        return x
    g = 10 ** (target_dbfs / 20) / rms
    g = min(g, 10 ** (18 / 20))     # never more than +18 dB (silence stays silence)
    return (x * g).astype(np.float32)


def limiter(x: np.ndarray, rate: int, ceiling_db: float = LIMIT_DBFS, lookahead_ms: float = 2.0, release_ms: float = 60.0) -> np.ndarray:
    """Look-ahead peak limiter: gain is reduced before a peak arrives, never clipped."""
    if x.size == 0:
        return x
    ceil = 10 ** (ceiling_db / 20)
    la = max(1, int(rate * lookahead_ms / 1000))
    ax = np.abs(x)
    # the peak in the next `la` samples (max filter via sliding window)
    pad = np.concatenate([ax, np.zeros(la, dtype=ax.dtype)])
    win = np.lib.stride_tricks.sliding_window_view(pad, la + 1)
    peak = win.max(axis=1)[: x.size]
    need = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    a_rel = math.exp(-1.0 / (rate * release_ms / 1000.0))
    # instant attack (take the minimum), smooth release back to 1.0
    gain = lfilter([1 - a_rel], [1, -a_rel], need)
    gain = np.minimum(gain, need)
    y = x * gain
    return np.clip(y, -ceil, ceil).astype(np.float32)


def exciter(x: np.ndarray, rate: int, mix: float = 0.10) -> np.ndarray:
    """Aural exciter: harmonics generated from the 3-6 kHz band, kept above 7 kHz, mixed in quietly.
    Gives the sparkle a studio condenser has and a 24 kHz TTS codec does not."""
    if rate < 32000 or x.size < 64:
        return x
    band = _filt("band", x, rate, [3000.0, 6000.0], 2)
    harm = np.tanh(band * 8.0) / 8.0
    harm = _bq("highpass", harm, rate, 8500.0, 0.707)
    harm = _bq("highpass", harm, rate, 8500.0, 0.707)
    return (x + harm * mix * 4.0).astype(np.float32)


# ------------------------------------------------------------------ the chain
def mic_chain(x: np.ndarray, rate: int) -> np.ndarray:
    if x.size == 0:
        return x
    y = x.astype(np.float32)
    y = _bq("highpass", y, rate, 80.0, 0.707)
    y = _bq("highpass", y, rate, 80.0, 0.707)                 # 24 dB/oct rumble floor
    y = _bq("peak", y, rate, 240.0, 0.9, -3.0)                 # the TTS voice is bass-heavy: mud out, clarity in
    y = _bq("peak", y, rate, 2800.0, 1.2, 3.0)                 # presence / intelligibility (kept below the sibilance band)
    if rate >= 32000:
        y = _bq("highshelf", y, rate, 9500.0, 0.7, 2.0)        # air
    y = exciter(y, rate)
    y = deess(y, rate)
    y = compress(y, rate)
    y = normalize(y)
    return limiter(y, rate)


def breath(rate: int, seconds: float | None = None, level: float = 0.012, rng=None) -> np.ndarray:
    """A quiet, natural inhale: soft low band plus a whisper of air, rising then falling."""
    rng = rng or _rng
    sec = seconds or (0.18 + rng.random() * 0.14)
    n = max(8, int(rate * sec))
    noise = rng.standard_normal(n).astype(np.float32)
    low = _filt("band", noise, rate, [250.0, 1600.0], 2)
    air = _filt("band", noise, rate, [3000.0, min(7000.0, rate / 2 - 100)], 2) * 0.35
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.clip(np.sin(np.pi * t), 0.0, 1.0) ** 2.2        # clip: sin(pi) is a tiny negative -> NaN under a fractional power
    mix = low + air
    out = mix / (np.max(np.abs(mix)) + 1e-6) * env * level
    return out.astype(np.float32)


def room_tone(rate: int, seconds: float, level: float = 0.00025, rng=None) -> np.ndarray:
    """Studio silence: a -72 dBFS pink-ish floor so the gaps are never a dead digital zero. Inaudible."""
    rng = rng or _rng
    n = int(rate * seconds)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    noise = rng.standard_normal(n).astype(np.float32)
    noise = _filt("low", noise, rate, 600.0, 1)
    return (noise / (np.max(np.abs(noise)) + 1e-6) * level).astype(np.float32)


def humanize_sentence(audio: np.ndarray, rate: int, *, first: bool, long_prev: bool, mood: str = "teach", seed: int | None = None,
                      plan=None) -> np.ndarray:
    """The sentence with a natural lead-in (sometimes a breath, always a small varying gap), the broadcast
    chain on the voice, and a short tail; levels are consistent sentence to sentence.
    With a seed the result is repeatable (same sentence, same audio), which keeps the synthesis cache exact.
    With a `plan` (voice/human.py) the delivery follows it: pace, beat before, level, mic distance, noises."""
    if audio.size == 0:
        return audio
    rng = np.random.default_rng(seed) if seed is not None else _rng
    if plan is not None and getattr(plan, "contour", "flat") not in ("flat", ""):
        from .intonation import apply as intonate

        audio = intonate(audio, rate, plan.contour, plan.strength)     # pitch and loudness pattern, timbre untouched
    voice = mic_chain(audio, rate)
    if plan is not None:
        from .human import render

        return render(voice, rate, plan, rng, first=first, long_prev=long_prev, mood=mood)
    parts = []
    p_breath = 0.5 if (first or long_prev) else 0.18
    if mood in ("hype", "excited"):
        p_breath += 0.15
    gap = 0.05 + rng.random() * (0.20 if not first else 0.06)
    parts.append(room_tone(rate, gap, rng=rng))
    if rng.random() < p_breath:
        parts.append(breath(rate, rng=rng))
        parts.append(room_tone(rate, 0.03 + rng.random() * 0.05, rng=rng))
    parts.append(voice)
    parts.append(room_tone(rate, 0.04 + rng.random() * 0.10, rng=rng))
    return np.concatenate(parts).astype(np.float32)
