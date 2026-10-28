"""Text-level human touches: fillers, tag questions, thinking pauses, self-talk.

Applied right before synthesis (after pronunciation rewriting). Kept light: a real streamer
says "okay, so" and "right?" sometimes, not every sentence. Never applied to disclaimers
or serious lines, and never inside numbers.
"""
from __future__ import annotations

import random
import re

_SENT = re.compile(r"(?<=[.!?])\s+")

OPENERS = {
    "teach": ["Okay, so", "So,", "Right,", "Look,", "Now,", "Alright,", "See,", "Here's the thing,"],
    "warm": ["Okay,", "Hey,", "So,", "Alright,", "Oh,"],
    "hype": ["Okay okay,", "Wait,", "Oh,", "Look at this,", "Hold on,", "Yo,"],
    "calm": ["Hmm,", "Okay,", "So,", "Let me think,", "Right,"],
    "cheerful": ["Okay,", "Oh nice,", "Love it,", "Alright,", "Good,", "Right,"],
    "show": ["Okay!", "Right,", "Let's go,", "Okay, chat,", "Here we go,", "Alright,"],
    "excited": ["Oh, look at this,", "Wait wait,", "Okay, this is it,", "Here we go,", "Oh!"],
    "curious": ["Hmm,", "Okay,", "Now,", "Question,", "So,"],
    "considerate": ["Okay.", "Alright,", "Look,"],
}
TAGS = {
    "teach": ["right?", "yeah?", "you see that?", "makes sense?"],
    "warm": ["right?", "yeah?"],
    "hype": ["right?!", "you see it?"],
    "calm": ["right?", "okay?"],
    "cheerful": ["right?", "yeah?", "love that."],
    "show": ["right?!", "you see it?", "let's go."],
    "excited": ["you see it?", "right?!"],
    "curious": ["right?", "what do you think?"],
    "considerate": ["okay?"],
}
THINKING = ["Let me look.", "Give me a second.", "Hmm.", "Let me check that."]
_COMMON_STARTERS = {"the", "this", "that", "these", "those", "price", "gold", "bitcoin", "if", "when", "so", "look", "you", "we", "it",
                    "here", "there", "now", "and", "but", "okay", "a", "an", "one", "every", "most", "some", "what", "which", "why", "how",
                    "once", "then", "before", "after", "notice", "watch", "see", "think", "remember", "say", "let", "i", "my", "our", "your"}
RESTARTS = ["wait, let me say that again.", "no, let me start that again.", "hang on, say it properly.", "actually, let me rephrase."]
_NUMBERISH = re.compile(r"\d")
_SERIOUS = re.compile(r"\b(not financial advice|education|disclaimer|risk warning|invalidat)", re.I)


class Imperfections:
    """Rare, human slips: a repeated first word under momentum, a sentence abandoned and restarted.
    Rate-limited across the whole stream: at most a few an hour, never two in a row, never on serious lines."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.last_false_start = 0.0
        self.last_restart = 0.0
        self.count = 0

    def apply(self, text: str, mood: str = "teach", now: float | None = None) -> str:
        import time as _t

        now = _t.time() if now is None else now
        if not text or mood in ("serious", "considerate") or _SERIOUS.search(text):
            return text
        sents = [s.strip() for s in _SENT.split(text.strip()) if s.strip()]
        cands = [i for i, s in enumerate(sents) if len(s.split()) >= 8 and not _NUMBERISH.search(s) and not s.startswith("[")]
        if not cands:
            return text
        # a restart: about one every 25 minutes of talking, and only on a long explanatory sentence
        if now - self.last_restart > 1500 and self.rng.random() < 0.06:
            i = self.rng.choice(cands)
            words = sents[i].split()
            cut = max(3, min(len(words) - 3, int(len(words) * (0.3 + self.rng.random() * 0.25))))
            head = " ".join(words[:cut]).rstrip(",;:")
            sents[i] = f"{head}... {self.rng.choice(RESTARTS)} {sents[i]}"
            self.last_restart = now
            self.count += 1
            return " ".join(sents)
        # a false start: a repeated first word, about one every 8 minutes, more under excitement
        p = 0.10 if mood in ("hype", "excited", "show") else 0.06
        if now - self.last_false_start > 480 and self.rng.random() < p:
            i = self.rng.choice(cands)
            words = sents[i].split()
            w = words[0].rstrip(",")
            if w.lower() in ("the", "this", "that", "so", "and", "it", "price", "if", "when", "look", "you", "we", "i"):
                sents[i] = f"{w}, {w.lower()} " + " ".join(words[1:])
                self.last_false_start = now
                self.count += 1
                return " ".join(sents)
        return text


def humanize_text(text: str, mood: str = "teach", seed: int | None = None) -> str:
    if mood == "serious" or not text:
        return text
    rnd = random.Random(seed if seed is not None else hash(text) & 0xFFFF)
    sents = [s.strip() for s in _SENT.split(text.strip()) if s.strip()]
    out = []
    for i, s in enumerate(sents):
        s2 = s
        # opener on the first sentence sometimes, on later ones rarely
        p_open = 0.28 if i == 0 else 0.07
        if rnd.random() < p_open and not re.match(r"^(okay|so|right|look|now|alright|see|hey|oh|wait|hmm|yo)\b", s2, re.I):
            op = rnd.choice(OPENERS.get(mood, OPENERS["teach"]))
            first = s2.split()[0].rstrip(",.") if s2.split() else ""
            # only lower-case a plain sentence starter; a name ("Maria, good one") keeps its capital
            if first.lower() in _COMMON_STARTERS and len(s2) > 1:
                s2 = s2[0].lower() + s2[1:]
            s2 = f"{op} {s2}"
        # thinking pause before a sentence that starts with a number or a level (sounds like reading the chart)
        if i > 0 and rnd.random() < 0.08 and re.match(r"^(The|That|This|Price|Gold|Bitcoin)\b", s2):
            s2 = rnd.choice(THINKING) + " " + s2
        # tag question on statements, not on questions/exclamations, not too often
        if s2.endswith(".") and len(s2.split()) >= 6 and rnd.random() < (0.12 if mood in ("teach", "warm") else 0.06):
            s2 = s2[:-1] + ", " + rnd.choice(TAGS.get(mood, TAGS["teach"]))
        # a mid-sentence breath before "because"/"but"/"and then"
        s2 = re.sub(r",\s+(because|but|and then|which means)\b", lambda m: f"... {m.group(1)}" if rnd.random() < 0.3 else m.group(0), s2, count=1)
        out.append(s2)
    return " ".join(out)
