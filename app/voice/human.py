"""The human layer: how a real host *delivers* a sentence, decided per sentence and rendered on the audio.

Text already carries the words (persona, disfluency.py). This module decides the delivery and renders it:

  plan_sentence(...)  -> Plan   what the sentence needs: pace, the beat before it, level, how close to the mic,
                                 whether it is an aside, a murmur, whether a breath or a mouth noise fits
  render(...)                    applies a Plan to synthesized audio (used by humanize_audio.humanize_sentence)

Cues the planner reads, the way a person would without thinking:
  * a list of three speeds up slightly; the risk / invalidation line slows down and gets a beat before it
  * a number gets a short landing pause before it; a question gets a little air after it
  * an aside (a callback to a viewer, "the wick thing from yesterday") is quicker and quieter, like a remark
  * a murmur ("mm", "okay", "right, so") while drawing is quiet and close, almost to himself
  * excitement leans back from the mic a touch; a serious point leans in
  * time of day drifts the voice: a little slower and warmer deep in the night, brighter at the London and
    New York opens; a long talking stretch adds a hint of roughness that clears after a quiet spell
  * now and then a lip smack before a line, an audible inhale before a long one, very rarely a swallow

Everything is small. The ear should never catch one effect; it should just stop noticing a machine.
"""
from __future__ import annotations

import math
import re
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .humanize_audio import _bq, _filt, breath, room_tone

# ------------------------------------------------------------------ cues
RISK_RE = re.compile(r"\b(invalidat\w*|where (the idea|it|this) (is|would be|'s|is proven) wrong|proves? (it|the idea|us) wrong|stop loss|the stop\b|risk\b|lose|losing|lost|wrong side|against you)\b", re.I)
NUMBER_RE = re.compile(r"\d|\b(thousand|hundred|percent|point \w+ \w+)\b", re.I)
LIST_RE = re.compile(r"\b(first|second|third|one,|two,|three,)\b", re.I)
ASIDE_RE = re.compile(r"^(welcome back|good to see you again|hey again)|\b(you asked|yesterday|earlier|last time|the follow-up|like i said|as i said|remember when|we talked about)\b", re.I)
POINT_RE = re.compile(r"\b(look at|watch this|see that|right here|this is the part|listen|the important bit)\b", re.I)
EXCITE_RE = re.compile(r"!|\b(whoa|wow|look at that|there it is|hold on)\b", re.I)
MURMURS = ["Mm.", "Okay.", "Right, so.", "Hm, let me see.", "Yeah.", "There.", "Okay, okay.", "Mm hm.", "Right."]


@dataclass
class Plan:
    speed: float = 1.0          # >1 faster (shorter)
    pre_gap: float = 0.0        # extra silence before the sentence, seconds
    post_gap: float = 0.0       # extra silence after, seconds
    level_db: float = 0.0       # offset from the normalised level
    proximity: float = 0.0      # -1 leaning back .. +1 leaning in
    breath: bool | None = None  # None: humanizer decides; True/False forces
    inhale: bool = False        # long audible inhale (before a long sentence)
    smack: bool = False         # lip smack before the line
    swallow: bool = False       # a swallow in the lead-in (rare)
    aside: bool = False
    murmur: bool = False
    warmth_db: float = 0.0      # low-shelf offset (time of day)
    presence_db: float = 0.0    # presence peak offset (time of day)
    roughness: float = 0.0      # 0..1 saturation from a long talking stretch
    contour: str = "statement"  # intonation shape: statement | question | continue | emphasis | flat
    key_st: float = 0.0         # per-sentence pitch offset in semitones (no two sentences in the same key)
    strength: float = 0.8       # how much of the contour to apply
    notes: list[str] = field(default_factory=list)


class TalkClock:
    """How much Haddan has talked in the last hour (for fatigue) and the last time he spoke."""

    def __init__(self) -> None:
        self._log: deque[tuple[float, float]] = deque()
        self.last_end = 0.0

    def note(self, seconds: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._log.append((now, seconds))
        self.last_end = now
        cutoff = now - 3600
        while self._log and self._log[0][0] < cutoff:
            self._log.popleft()

    def talked_last_hour(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return sum(s for t, s in self._log if t >= now - 3600)

    def fatigue(self, now: float | None = None) -> float:
        """0 after a quiet hour, 1 after talking most of the last hour without a break."""
        f = self.talked_last_hour(now) / 3600.0
        return float(min(1.0, max(0.0, (f - 0.45) / 0.45)))


def daypart(now: float | None = None) -> tuple[float, float, float, str]:
    """(speed factor, warmth dB, presence dB, label) from the UTC hour: nights slower and warmer, opens brighter."""
    h = time.gmtime(now or time.time()).tm_hour
    if 22 <= h or h < 5:
        return 0.975, 1.0, -0.5, "night"
    if 7 <= h < 10 or 13 <= h < 16:
        return 1.01, 0.0, 1.0, "open"
    return 1.0, 0.3, 0.0, "day"


def plan_sentence(sentence: str, *, mood: str = "teach", index: int = 0, total: int = 1, rng: np.random.Generator | None = None,
                  clock: TalkClock | None = None, engine_sets_rate: bool = False, override: dict | None = None, now: float | None = None) -> Plan:
    rng = rng or np.random.default_rng(abs(hash(sentence)) & 0xFFFF)
    s = sentence.strip()
    words = len(s.split())
    p = Plan()
    spd, p.warmth_db, p.presence_db, label = daypart(now)
    p.notes.append(label)
    if clock is not None:
        p.roughness = clock.fatigue(now)
        if p.roughness > 0.3:
            p.notes.append(f"fatigue {p.roughness:.1f}")
    # mood baseline
    if mood in ("hype", "excited"):
        spd *= 1.04; p.proximity -= 0.5; p.level_db += 0.3
    elif mood in ("considerate", "serious"):
        spd *= 0.96; p.proximity += 0.5
    elif mood == "calm":
        spd *= 0.98
    # content cues
    if ASIDE_RE.search(s):
        p.aside = True; spd *= 1.06; p.level_db -= 2.0; p.proximity += 0.3; p.notes.append("aside")
    if RISK_RE.search(s) and mood not in ("hype", "excited"):
        spd *= 0.94; p.pre_gap += 0.35; p.proximity += 0.6; p.notes.append("risk line")
    if LIST_RE.search(s) or s.count(", ") >= 3:
        spd *= 1.04; p.notes.append("list")
    if NUMBER_RE.search(s):
        p.pre_gap += 0.2 + float(rng.random()) * 0.3; spd *= 0.98; p.notes.append("number")
    if POINT_RE.search(s):
        spd *= 0.95; p.proximity += 0.5; p.notes.append("pointing")
    if EXCITE_RE.search(s) and words <= 8:
        spd *= 1.03; p.level_db += 0.5; p.proximity -= 0.6; p.notes.append("excited")
    if s.endswith("?"):
        p.post_gap += 0.3 + float(rng.random()) * 0.4; p.notes.append("question")
    if words >= 26:
        p.notes.append("long")
    if words <= 3 and index == 0:
        p.post_gap += 0.15                      # "Okay." then a beat
    # intonation: the English rising/falling rulebook (voice/intonation.py) decides the pattern for this sentence
    from .intonation import classify

    p.contour = classify(s, index, total)
    p.key_st = 0.0                                  # the pitch is the host's own, always
    p.strength = 0.85 + float(rng.random()) * 0.45
    p.notes.append(p.contour)
    # mouth noises: rare, never on an aside or a murmur
    if not p.aside and rng.random() < 0.07:
        p.smack = True
    if index == 0 and rng.random() < 0.025:
        p.swallow = True
    # person-to-person variation so no two sentences are delivered identically
    spd *= 1.0 + (float(rng.random()) - 0.5) * 0.04
    p.level_db += (float(rng.random()) - 0.5) * 1.2
    p.proximity += (float(rng.random()) - 0.5) * 0.4
    if override:
        for k, v in override.items():
            setattr(p, k, v)
        if override.get("murmur"):
            p.level_db = -4.5; p.proximity += 0.8; p.breath = False; p.smack = False; p.inhale = False; p.pre_gap = 0.0
            p.contour = "flat"; p.key_st = 0.0
            p.notes.append("murmur")
    p.speed = 1.0 if engine_sets_rate else float(min(1.12, max(0.88, spd)))
    p.proximity = float(min(1.0, max(-1.0, p.proximity)))
    return p


# ------------------------------------------------------------------ audio pieces
def time_stretch(x: np.ndarray, rate: int, factor: float) -> np.ndarray:
    """Change pace without changing pitch. factor > 1 = faster. WSOLA (waveform-similarity overlap-add): for the
    small factors used here it is cleaner than a phase vocoder, needs no extra library, and is a few ms per sentence."""
    if abs(factor - 1.0) < 0.008 or x.size < int(rate * 0.25):
        return x
    y = _wsola(x, rate, factor)
    return y if y.size and np.isfinite(y).all() else x


def _wsola(x: np.ndarray, rate: int, factor: float, win_ms: float = 30.0, tol_ms: float = 5.0) -> np.ndarray:
    n = int(rate * win_ms / 1000) & ~1
    hop = n // 2
    hop_in = max(1, int(round(hop * factor)))
    tol = int(rate * tol_ms / 1000)
    win = np.hanning(n).astype(np.float32)
    src = np.concatenate([x.astype(np.float32), np.zeros(2 * n, dtype=np.float32)])
    out_len = int(x.size / factor) + 2 * n
    out = np.zeros(out_len, dtype=np.float32)
    norm = np.zeros(out_len, dtype=np.float32)
    pos_in, pos_out, prev = 0, 0, None
    while pos_out + n < out_len and pos_in + n + hop + tol < src.size:
        if prev is not None:
            lo = max(0, pos_in - tol)
            seg = src[lo:pos_in + tol + n]
            if seg.size >= n:
                c = np.correlate(seg, prev, mode="valid")
                pos_in = lo + int(np.argmax(c))
        out[pos_out:pos_out + n] += src[pos_in:pos_in + n] * win
        norm[pos_out:pos_out + n] += win
        prev = src[pos_in + hop:pos_in + hop + n]
        pos_out += hop
        pos_in += hop_in
    y = out[:pos_out + hop] / np.maximum(norm[:pos_out + hop], 1e-3)
    return y.astype(np.float32)


# ------------------------------------------------------------------ intonation
# semitone contour over five slices of the sentence, and a gain contour (dB) for emphasis and trailing off
CONTOURS = {
    "question":  ([0.0, 0.1, 0.4, 1.2, 2.6], [0.0, 0.0, 0.2, 0.6, 1.0]),
    "statement": ([0.6, 1.0, 0.3, -0.5, -1.7], [0.6, 1.0, 0.0, -0.7, -1.8]),
    "continue":  ([0.2, 0.6, 0.2, 0.3, 1.0], [0.0, 0.4, 0.0, 0.0, -0.5]),
    "emphasis":  ([1.6, 2.0, 0.8, 0.0, -1.0], [1.6, 2.0, 0.5, 0.0, -1.0]),
    "flat":      ([0.0] * 5, [0.0] * 5),
}


def _slices(y: np.ndarray, rate: int, k: int = 5) -> list[int]:
    """Boundaries for k slices, each snapped to the quietest point near an equal division (between words, not inside one)."""
    n = y.size
    hop = max(1, int(rate * 0.01))
    frames = max(1, n // hop)
    env = np.sqrt((y[:frames * hop].reshape(frames, hop) ** 2).mean(axis=1) + 1e-9)
    bounds = [0]
    for i in range(1, k):
        target = int(n * i / k)
        lo, hi = max(hop, target - int(rate * 0.12)), min(n - hop, target + int(rate * 0.12))
        if hi <= lo + hop:
            bounds.append(target)
            continue
        seg = env[lo // hop:hi // hop]
        bounds.append(lo + int(np.argmin(seg)) * hop if seg.size else target)
    bounds.append(n)
    return bounds


def pitch_shift(x: np.ndarray, rate: int, semitones: float) -> np.ndarray:
    """Shift pitch, keep duration: resample (changes pitch and length) then WSOLA back to the original length."""
    if abs(semitones) < 0.08 or x.size < int(rate * 0.06):
        return x
    from fractions import Fraction
    from scipy.signal import resample_poly

    f = 2 ** (semitones / 12.0)
    fr = Fraction(1.0 / f).limit_denominator(96)
    y = resample_poly(x, fr.numerator, fr.denominator).astype(np.float32)      # length / f
    z = _wsola(y, rate, y.size / max(1, x.size)) if y.size > int(rate * 0.06) else y
    if z.size > x.size:
        z = z[:x.size]
    elif z.size < x.size:
        z = np.concatenate([z, np.zeros(x.size - z.size, dtype=np.float32)])
    return z.astype(np.float32)


def shape_intonation(y: np.ndarray, rate: int, contour: str, strength: float, key_st: float, pitch: bool = False) -> np.ndarray:
    """Shape the LOUDNESS of the sentence the way a speaker does: lean on the stress, trail off at the end of a statement,
    lift at the end of a question. Pitch is left exactly as the voice engine produced it: shifting pitch by resampling moves
    the resonances of the voice too, and that reads as a different person. The host's timbre is never touched."""
    if y.size < int(rate * 0.35) or contour not in CONTOURS:
        return y
    st_c, db_c = CONTOURS[contour]
    bounds = _slices(y, rate, len(st_c))
    parts = []
    xf = int(rate * 0.015)
    for i in range(len(bounds) - 1):
        seg = y[bounds[i]:bounds[i + 1]]
        if pitch:
            st = max(-3.0, min(3.0, st_c[i] * strength + key_st))
            seg = pitch_shift(seg, rate, st)
        seg = (seg * 10 ** (db_c[i] * strength / 20)).astype(np.float32)
        parts.append(seg)
    out = parts[0]
    for p in parts[1:]:
        k = min(xf, out.size, p.size)
        if k > 8:
            r = np.linspace(0, 1, k, dtype=np.float32)
            out = np.concatenate([out[:-k], out[-k:] * (1 - r) + p[:k] * r, p[k:]])
        else:
            out = np.concatenate([out, p])
    return out.astype(np.float32)


def proximity(x: np.ndarray, rate: int, amount: float) -> np.ndarray:
    """Lean in (+): a touch more low end and level. Lean back (-): thinner, a touch quieter."""
    if abs(amount) < 0.05 or x.size == 0:
        return x
    y = _bq("lowshelf", x, rate, 160.0, 0.8, 1.6 * amount)
    if amount < 0:
        y = _bq("highpass", y, rate, 110.0 + 50.0 * -amount, 0.707)
    return (y * 10 ** (0.6 * amount / 20)).astype(np.float32)


def tone_of_day(x: np.ndarray, rate: int, warmth_db: float, presence_db: float) -> np.ndarray:
    y = x
    if abs(warmth_db) >= 0.2:
        y = _bq("lowshelf", y, rate, 180.0, 0.8, warmth_db)
    if abs(presence_db) >= 0.2:
        y = _bq("peak", y, rate, 3000.0, 1.0, presence_db)
    return y.astype(np.float32)


def roughen(x: np.ndarray, amount: float) -> np.ndarray:
    """A hint of vocal roughness after a long talking stretch: soft saturation mixed in quietly."""
    if amount <= 0.02 or x.size == 0:
        return x
    m = 0.3 * float(min(1.0, amount))
    sat = np.tanh(2.6 * x) / 2.6
    return ((1 - m) * x + m * sat).astype(np.float32)


def lip_smack(rate: int, rng: np.random.Generator, level: float = 0.007) -> np.ndarray:
    n = int(rate * (0.018 + rng.random() * 0.012))
    noise = rng.standard_normal(n).astype(np.float32)
    band = _filt("band", noise, rate, [1500.0, min(6500.0, rate / 2 - 100)], 2)
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = (t < 0.15) * (t / 0.15) + (t >= 0.15) * np.exp(-(t - 0.15) * 9.0)
    out = band / (np.max(np.abs(band)) + 1e-6) * env * level
    return out.astype(np.float32)


def swallow(rate: int, rng: np.random.Generator, level: float = 0.004) -> np.ndarray:
    n = int(rate * (0.08 + rng.random() * 0.05))
    noise = rng.standard_normal(n).astype(np.float32)
    low = _filt("low", noise, rate, 260.0, 2)
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.clip(np.sin(np.pi * t), 0.0, 1.0) ** 1.6
    out = low / (np.max(np.abs(low)) + 1e-6) * env * level
    return out.astype(np.float32)


def inhale(rate: int, rng: np.random.Generator) -> np.ndarray:
    return breath(rate, seconds=0.32 + float(rng.random()) * 0.18, level=0.015, rng=rng)


def render(voice: np.ndarray, rate: int, plan: Plan, rng: np.random.Generator, *, first: bool, long_prev: bool, mood: str) -> np.ndarray:
    """Apply a Plan to a mic-chained sentence: pace, tone, proximity, roughness, lead-in noises and gaps."""
    y = voice
    if plan.speed != 1.0:
        y = time_stretch(y, rate, plan.speed)
    y = tone_of_day(y, rate, plan.warmth_db, plan.presence_db)
    y = proximity(y, rate, plan.proximity)
    y = roughen(y, plan.roughness)
    if plan.level_db:
        y = (y * 10 ** (plan.level_db / 20)).astype(np.float32)
    parts: list[np.ndarray] = []
    gap = 0.05 + float(rng.random()) * (0.20 if not first else 0.06) + plan.pre_gap
    parts.append(room_tone(rate, gap, rng=rng))
    if plan.swallow:
        parts.append(swallow(rate, rng))
        parts.append(room_tone(rate, 0.08 + float(rng.random()) * 0.08, rng=rng))
    if plan.smack:
        parts.append(lip_smack(rate, rng))
        parts.append(room_tone(rate, 0.03 + float(rng.random()) * 0.04, rng=rng))
    # breaths are OFF: on the stream they read as laboured and add an AI feel. The host decided; room tone only.
    want_breath = False
    plan.inhale = False
    if plan.inhale or want_breath:
        from . import sfx

        real = sfx.get("inhale" if plan.inhale else "breath", rate) if sfx.available() else None
        if real is not None:
            parts.append(real)
        elif plan.inhale:
            parts.append(inhale(rate, rng))
        else:
            parts.append(breath(rate, rng=rng))
        parts.append(room_tone(rate, 0.03 + float(rng.random()) * 0.06, rng=rng))
    parts.append(y)
    parts.append(room_tone(rate, 0.04 + float(rng.random()) * 0.10 + plan.post_gap, rng=rng))
    return np.concatenate(parts).astype(np.float32)


def describe(plan: Plan) -> str:
    bits = [f"x{plan.speed:.2f}"]
    if plan.pre_gap:
        bits.append(f"+{plan.pre_gap:.2f}s before")
    if abs(plan.level_db) >= 0.8:
        bits.append(f"{plan.level_db:+.1f} dB")
    if abs(plan.proximity) >= 0.3:
        bits.append("lean " + ("in" if plan.proximity > 0 else "back"))
    bits += [n for n in plan.notes if n not in ("day",)]
    if plan.smack:
        bits.append("smack")
    if plan.inhale:
        bits.append("inhale")
    return ", ".join(bits)
