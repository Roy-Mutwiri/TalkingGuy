"""Rising and falling intonation, the way English speakers do it, applied to the host's own voice.

The rulebook (standard English intonation patterns):
  FALL       statements, wh-questions (what/where/why/how/which/who), commands, exclamations, the LAST item of a list
  RISE       yes/no questions (do/is/can/will...), requests, unfinished thoughts (a clause before a comma, a sentence
             that hands over to the next), list items before the last, echo and check questions ("Four thousand?")
  FALL_RISE  hedges and partial agreement ("it might hold", "I think", "maybe", "usually"), warnings, polite corrections
  RISE_FALL  strong surprise or emphasis ("look at that!", "wow", a short exclamation)
  TAG        the statement falls, the tag question ("..., right?") rises
  ALT        "A or B?": the first alternative rises, the last falls
  LIST       "first..., second..., third...": every item rises, the last one falls

How it is applied without changing WHO is speaking: the WORLD vocoder splits the audio into pitch, spectral envelope
(the resonances that make a voice recognisable) and breathiness. Only the pitch track is reshaped; envelope and
breathiness go back untouched. Resampling-based shifting moves the envelope too and reads as a different person.

Loudness follows the same shape (lean on the stress, trail off on a fall, lift on a rise) so pitch and energy agree,
as they do in real speech. Amounts stay under four semitones. Unvoiced sounds are never touched.
"""
from __future__ import annotations

import logging
import re

import numpy as np

log = logging.getLogger("voice")

FRAME_MS = 5.0
MAX_ST = 4.0

YESNO_RE = re.compile(r"^(do|does|did|is|are|was|were|can|could|will|would|should|have|has|had|am|shall|may|might|isn't|aren't|don't|doesn't|didn't|won't|wouldn't|can't|couldn't)\b", re.I)
WH_RE = re.compile(r"^(what|where|when|why|how|which|who|whose|whom)\b", re.I)
TAG_RE = re.compile(r",\s*(right|yeah|okay|ok|no|isn't it|is it|see that|see it|makes sense|you see it|you see that|agreed|yes)\s*\?\s*$", re.I)
ALT_RE = re.compile(r"\bor\b", re.I)
HEDGE_RE = re.compile(r"\b(maybe|might|may\b|probably|perhaps|possibly|i think|not sure|could be|sort of|kind of|usually|sometimes|tends? to|more or less|in theory|on paper|unless|although|though)\b", re.I)
COMMAND_RE = re.compile(r"^(look|watch|type|wait|notice|remember|take|mark|draw|check|say|think|don't|never|always|stop|hold on|listen|see|imagine|ask|put|keep|let's|let me)\b", re.I)
SURPRISE_RE = re.compile(r"\b(whoa|wow|look at that|there it is|hold on|no way|oh)\b|!", re.I)
LIST_RE = re.compile(r"\b(first|second|third|one,|two,|three,)\b", re.I)
HANDOFF_RE = re.compile(r"\b(and|but|so|because|which|then|while|if|when)\s*[,.]?\s*$", re.I)
_TAGS = re.compile(r"\[[^\]]{1,20}\]")


def classify(sentence: str, index: int = 0, total: int = 1) -> str:
    """The intonation pattern a native speaker would use for this sentence in this position."""
    s = _TAGS.sub("", sentence).strip()
    if not s:
        return "flat"
    words = len(s.split())
    last = index >= total - 1
    if s.endswith("?"):
        if TAG_RE.search(s):
            return "tag"
        if ALT_RE.search(s) and words >= 4:
            return "alt"                                # "support or resistance?" before the yes/no rule
        if YESNO_RE.match(s):
            return "rise"
        if WH_RE.match(s):
            return "fall"
        return "rise"                                   # check / echo question: "Four thousand?"
    if s.endswith("!"):
        return "rise_fall" if (words <= 7 or SURPRISE_RE.search(s)) else "fall"
    commas = s.count(",")
    if (LIST_RE.search(s) and commas >= 1) or commas >= 3:
        return "list"
    if s.endswith(",") or (not last and HANDOFF_RE.search(s)):
        return "rise"                                   # unfinished thought
    if SURPRISE_RE.search(s) and words <= 8:
        return "rise_fall"
    if HEDGE_RE.search(s) and not COMMAND_RE.match(s):
        return "fall_rise"
    return "fall"                                       # statements, commands, wh-questions


# ---------------------------------------------------------------- contours
def _shape(pattern: str, u: np.ndarray, strength: float) -> tuple[np.ndarray, np.ndarray]:
    """(semitones, dB) along one phrase, u = position 0..1 over its voiced span."""
    st = np.zeros_like(u)
    db = np.zeros_like(u)
    if pattern == "fall":
        st = np.where(u < 0.18, 0.9 * (1 - u / 0.18), 0.0) + np.where(u > 0.62, -2.4 * (u - 0.62) / 0.38, 0.0)
        db = np.where(u < 0.25, 0.8, 0.0) + np.where(u > 0.7, -1.8 * (u - 0.7) / 0.3, 0.0)
    elif pattern == "rise":
        st = np.where(u > 0.6, 2.9 * ((u - 0.6) / 0.4) ** 1.3, 0.0) + np.where(u < 0.15, 0.3, 0.0)
        db = np.where(u > 0.7, 0.9 * (u - 0.7) / 0.3, 0.0)
    elif pattern == "fall_rise":
        st = np.where(u < 0.72, -1.7 * np.clip((u - 0.3) / 0.42, 0, 1), -1.7 + 3.2 * (u - 0.72) / 0.28)
        db = np.where(u > 0.72, 0.5 * (u - 0.72) / 0.28, 0.0)
    elif pattern == "rise_fall":
        st = np.where(u < 0.62, 3.1 * np.clip((u - 0.15) / 0.47, 0, 1), 3.1 - 5.0 * (u - 0.62) / 0.38)
        db = np.where(u < 0.65, 1.6 * np.clip((u - 0.1) / 0.5, 0, 1), 1.6 - 2.6 * (u - 0.65) / 0.35)
    elif pattern == "flat":
        pass
    return st * strength, db * strength


def _phrases(voiced: np.ndarray, min_gap_frames: int) -> list[tuple[int, int]]:
    """Voiced spans separated by silences long enough to be a phrase break (frame indices, [start, end))."""
    idx = np.flatnonzero(voiced)
    if idx.size == 0:
        return []
    spans = []
    start = idx[0]
    prev = idx[0]
    for i in idx[1:]:
        if i - prev > min_gap_frames:
            spans.append((start, prev + 1))
            start = i
        prev = i
    spans.append((start, prev + 1))
    return spans


def contour(f0: np.ndarray, pattern: str, strength: float) -> tuple[np.ndarray, np.ndarray]:
    """Semitone and dB tracks (per frame) for the whole sentence, from the pattern and the voiced phrases."""
    n = f0.size
    st = np.zeros(n)
    db = np.zeros(n)
    voiced = f0 > 0
    spans = _phrases(voiced, int(150 / FRAME_MS))
    if not spans:
        return st, db
    # patterns that work phrase by phrase
    if pattern in ("list", "tag", "alt"):
        parts = spans if len(spans) >= 2 else [spans[0]]
        for k, (a, b) in enumerate(parts):
            local = "fall" if k == len(parts) - 1 else "rise"
            if pattern == "tag" and k == len(parts) - 1:
                local = "rise"
            if pattern == "tag" and k < len(parts) - 1:
                local = "fall"
            u = np.linspace(0, 1, b - a)
            s_, d_ = _shape(local, u, strength * (1.15 if pattern == "alt" else 1.0))
            st[a:b] = s_
            db[a:b] = d_
        if len(spans) == 1 and pattern == "alt":          # no pause to split on: rise then fall inside the one phrase
            a, b = spans[0]
            u = np.linspace(0, 1, b - a)
            st[a:b], db[a:b] = _shape("rise_fall", u, strength * 0.8)
        return st, db
    # one shape over the whole voiced extent: the nucleus is the last phrase, the onset the first
    a, b = spans[0][0], spans[-1][1]
    u = np.linspace(0, 1, b - a)
    st[a:b], db[a:b] = _shape(pattern, u, strength)
    return st, db


def _smooth(x: np.ndarray, frames: int) -> np.ndarray:
    if frames <= 1 or x.size < frames:
        return x
    k = np.ones(frames) / frames
    return np.convolve(x, k, mode="same")


def apply(y: np.ndarray, rate: int, pattern: str, strength: float = 1.0) -> np.ndarray:
    """Reshape the pitch (and loudness) of one sentence to the pattern. Timbre untouched. Falls back to the input."""
    if pattern in ("flat", "") or y.size < int(rate * 0.45):
        return y
    try:
        import pyworld as pw

        x = np.ascontiguousarray(y.astype(np.float64))
        f0, t = pw.dio(x, rate, frame_period=FRAME_MS, f0_floor=60.0, f0_ceil=400.0)
        f0 = pw.stonemask(x, f0, t, rate)
        if int((f0 > 0).sum()) < 20:
            return y
        st, db = contour(f0, pattern, strength)
        st = np.clip(_smooth(st, int(70 / FRAME_MS)), -MAX_ST, MAX_ST)
        db = _smooth(db, int(90 / FRAME_MS))
        sp = pw.cheaptrick(x, f0, t, rate)
        ap = pw.d4c(x, f0, t, rate)
        f0m = np.where(f0 > 0, f0 * 2 ** (st / 12.0), 0.0)
        z = pw.synthesize(f0m, sp, ap, rate, FRAME_MS).astype(np.float32)
        if z.size > x.size:
            z = z[:x.size]
        elif z.size < x.size:
            z = np.concatenate([z, np.zeros(x.size - z.size, dtype=np.float32)])
        # loudness follows the melody
        gain_frames = 10 ** (db / 20.0)
        gain = np.interp(np.arange(z.size) / rate, t, gain_frames).astype(np.float32)
        z = z * gain
        peak = float(np.max(np.abs(z))) or 1.0
        src_peak = float(np.max(np.abs(y))) or 1.0
        if peak > src_peak * 1.15:
            z = z * (src_peak * 1.15 / peak)
        return z.astype(np.float32)
    except Exception as exc:  # noqa: BLE001
        log.debug("intonation skipped: %s", exc)
        return y
