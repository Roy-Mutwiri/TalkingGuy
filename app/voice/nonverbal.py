"""Non-verbal layer: decides when Theo laughs, chuckles, sighs, gasps, groans, clears his throat or sniffs.

The brain may write tags itself (see tags.py); this layer adds them where a person would make the sound
and the brain did not, with discipline: at most one per utterance, a minimum gap between sounds, never on
disclaimers, numbers-only lines or recaps, placed at sentence boundaries so speech stays intelligible.

Rules of thumb (from watching good hosts): a chuckle lands on a self-deprecating line or a light tease,
a laugh on a shared win, a sigh before a considerate reply or an honest "it's boring", a gasp on a real
move, a groan on a classic beginner mistake, a throat-clear when switching to a serious point after a long
quiet, a sniff very rarely. Energy raises frequency; seriousness removes it entirely.
"""
from __future__ import annotations

import random
import re
import time

from .tags import has_tags

_SENT = re.compile(r"(?<=[.!?])\s+")

# per mood: probability of adding a sound to an utterance, and the weighted sound palette
MOOD_PALETTE: dict[str, tuple[float, dict[str, float]]] = {
    "excited": (0.55, {"laugh": 0.6, "chuckle": 0.4}),
    "hype": (0.45, {"laugh": 0.5, "chuckle": 0.5}),
    "cheerful": (0.40, {"chuckle": 0.6, "laugh": 0.4}),
    "show": (0.25, {"chuckle": 0.6, "clear throat": 0.2, "laugh": 0.2}),
    "warm": (0.20, {"chuckle": 1.0}),
    "curious": (0.15, {"chuckle": 0.5, "clear throat": 0.5}),
    "teach": (0.12, {"chuckle": 0.5, "clear throat": 0.3, "sniff": 0.2}),
    "considerate": (0.50, {"sigh": 1.0}),
    "calm": (0.10, {"clear throat": 1.0}),      # sighs come from real cues (a loss, a boring chart) or the considerate mood only
    "serious": (0.0, {}),
}

# wording that strongly suggests a sound regardless of mood (first match wins)
CUES = [
    (re.compile(r"\b(my first stop loss|i did that too|been there|guilty|i've done|classic beginner|rookie)\b", re.I), "chuckle", 0.8),
    (re.compile(r"\b(you spotted it|nailed it|exactly|you lot|love that|yes,? [A-Z])", re.I), "laugh", 0.6),
    (re.compile(r"\b(stings|sorry|that hurts|rough|tough one|it happens to everyone|frustrating)\b", re.I), "sigh", 0.8),
    (re.compile(r"\b(boring|nothing happening|slow chart|quiet session|waiting game)\b", re.I), "sigh", 0.7),
    (re.compile(r"\b(whoa|look at this|look at that|just ripped|just moved|there it is|hold on)\b", re.I), "gasp", 0.6),
    (re.compile(r"\b(moved the stop|revenge|chased|fomo|doubled down|averaged down)\b", re.I), "groan", 0.6),
    (re.compile(r"\b(okay,? serious|let's get serious|the risk line|this is the part|listen)\b", re.I), "clear throat", 0.5),
]
NEVER = re.compile(r"\b(not financial advice|educational|guarantee|disclaimer|risk warning)\b|^\s*[\d.,%+\- ]+$", re.I)
RECAP = re.compile(r"\b(recap|lock it in|take home|bottom line|summing up)\b", re.I)


class NonVerbal:
    def __init__(self, min_gap_s: float = 35.0, energy: float = 0.85, rng: random.Random | None = None) -> None:
        self.min_gap_s = min_gap_s
        self.energy = max(0.0, min(1.0, energy))
        self.rng = rng or random.Random()
        self.last_ts = 0.0
        self.last_sound = ""
        self.count = 0

    def _pick(self, palette: dict[str, float]) -> str:
        items = [(k, w) for k, w in palette.items() if k != self.last_sound] or list(palette.items())
        r = self.rng.random() * sum(w for _, w in items)
        for k, w in items:
            r -= w
            if r <= 0:
                return k
        return items[-1][0]

    def decorate(self, text: str, mood: str | None, *, now: float | None = None, force: str | None = None) -> str:
        """Return the text with at most one new tag placed at a sentence boundary, or unchanged."""
        now = time.time() if now is None else now
        if not text or has_tags(text) or NEVER.search(text) or RECAP.search(text):
            return text
        mood = mood or "teach"
        sound: str | None = force
        if sound is None:
            for rx, s, p in CUES:
                if rx.search(text) and self.rng.random() < p * (0.6 + 0.4 * self.energy):
                    sound = s
                    break
        if sound is None:
            prob, palette = MOOD_PALETTE.get(mood, MOOD_PALETTE["teach"])
            prob *= 0.5 + 0.5 * self.energy
            if not palette or self.rng.random() >= prob:
                return text
            sound = self._pick(palette)
        if now - self.last_ts < self.min_gap_s and not force:
            return text
        sents = _SENT.split(text.strip())
        # placement: sighs and throat-clears lead the utterance; laughs/chuckles/gasps follow the first sentence that earned them
        earned = next((i for i, s in enumerate(sents) if any(rx.search(s) for rx, _, _ in CUES) or s.endswith("!")), None)
        if sound in ("sigh", "clear throat", "sniff") or len(sents) == 1 or earned is None:
            out = f"[{sound}] " + text.strip()           # leads the line: a chuckle before a tease, a sigh before the hard part
        else:
            sents[earned] = sents[earned] + f" [{sound}]"  # follows the sentence that earned it
            out = " ".join(sents)
        self.last_ts, self.last_sound, self.count = now, sound, self.count + 1
        return out
