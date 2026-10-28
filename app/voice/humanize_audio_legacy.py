"""Make synthesized speech sound like a person on a microphone.

Applied to each sentence after synthesis (vectorised with scipy, a few ms per sentence):
  - mic chain: gentle high-pass, a little presence, soft compression + limiter
  - breaths: a short, quiet inhale before some sentences (synthesized, shaped noise)
  - natural gaps: varying silence between sentences, never a hard digital cut
  - room tone: a faint noise floor under everything so there is never dead silence
All effects are subtle on purpose; the goal is natural, not theatrical.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter

_rng = np.random.default_rng(7)
_cache: dict = {}


def _coef(kind: str, rate: int, fc, order: int = 2):
    key = (kind, rate, fc if not isinstance(fc, list) else tuple(fc), order)
    if key not in _cache:
        _cache[key] = butter(order, fc, btype=kind, fs=rate)
    return _cache[key]


def _filt(kind: str, x: np.ndarray, rate: int, fc, order: int = 2) -> np.ndarray:
    b, a = _coef(kind, rate, fc, order)
    return lfilter(b, a, x).astype(np.float32)


def compress(x: np.ndarray, rate: int, threshold: float = 0.33, ratio: float = 2.6, makeup: float = 1.12) -> np.ndarray:
    """Envelope follower (fast attack, slow release) + gain computer + limiter."""
    if x.size == 0:
        return x
    env = np.abs(x).astype(np.float32)
    # release-smoothed envelope via a one-pole low-pass on the rectified signal (80 ms)
    b, a = _coef("low", rate, 12.0, 1)
    sm = lfilter(b, a, env).astype(np.float32)
    # fast attack: take the max of the smoothed and a lightly smoothed (5 ms) envelope
    b2, a2 = _coef("low", rate, 200.0, 1)
    fast = lfilter(b2, a2, env).astype(np.float32)
    sm = np.maximum(sm, fast)
    gain = np.ones_like(sm)
    over = sm > threshold
    gain[over] = (threshold + (sm[over] - threshold) / ratio) / sm[over]
    y = x * gain * makeup
    return np.clip(y, -0.95, 0.95).astype(np.float32)


def mic_chain(x: np.ndarray, rate: int) -> np.ndarray:
    if x.size == 0:
        return x
    y = _filt("high", x, rate, 85.0, 2)
    pres = _filt("band", y, rate, [1800.0, 4200.0], 2)
    y = (y + pres * 0.22).astype(np.float32)       # ~ +1.7 dB presence
    return compress(y, rate)


def breath(rate: int, seconds: float | None = None, level: float = 0.04) -> np.ndarray:
    """A quiet inhale: band-limited noise with a rising-then-falling envelope."""
    sec = seconds or (0.2 + _rng.random() * 0.16)
    n = int(rate * sec)
    noise = _rng.standard_normal(n).astype(np.float32)
    noise = _filt("band", noise, rate, [350.0, 2800.0], 2)
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.clip(np.sin(np.pi * t), 0.0, 1.0) ** 1.6   # clip: sin(pi) is a tiny negative -> NaN under a fractional power
    out = noise / (np.max(np.abs(noise)) + 1e-6) * env * level
    return out.astype(np.float32)


def room_tone(rate: int, seconds: float, level: float = 0.003) -> np.ndarray:
    n = int(rate * seconds)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    noise = _rng.standard_normal(n).astype(np.float32)
    noise = _filt("low", noise, rate, 900.0, 1)
    return (noise / (np.max(np.abs(noise)) + 1e-6) * level).astype(np.float32)


def humanize_sentence(audio: np.ndarray, rate: int, *, first: bool, long_prev: bool, mood: str = "teach") -> np.ndarray:
    """Return the sentence with a natural lead-in: sometimes a breath, always a small, varying gap,
    then the processed voice, then a tail of room tone instead of a hard cut."""
    if audio.size == 0:
        return audio
    voice = mic_chain(audio, rate)
    parts = []
    p_breath = 0.55 if (first or long_prev) else 0.22
    if mood == "hype":
        p_breath += 0.15
    gap = 0.06 + _rng.random() * (0.22 if not first else 0.08)
    parts.append(room_tone(rate, gap))
    if _rng.random() < p_breath:
        parts.append(breath(rate))
        parts.append(room_tone(rate, 0.04 + _rng.random() * 0.06))
    tone = room_tone(rate, voice.size / rate + 0.05)[: voice.size]      # a hair longer, then cut to size
    parts.append(voice + tone if tone.size == voice.size else voice)
    parts.append(room_tone(rate, 0.05 + _rng.random() * 0.12))
    return np.concatenate(parts).astype(np.float32)
