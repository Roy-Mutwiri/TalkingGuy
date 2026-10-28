"""Non-verbal tags in spoken text: [laughs] [chuckles] [sighs] [clears throat] [gasps] [groans] [sniffs].

The brain writes them in square brackets inside the text it wants spoken. An expressive engine
(Chatterbox-Turbo) performs them; a plain engine (Edge, Kokoro) gets the text with the tags removed
so it never reads the word "laughs" aloud; captions never show them.
"""
from __future__ import annotations

import re

# what the brain may write -> the engine token (Chatterbox-Turbo vocabulary)
CANON = {
    "laugh": "laugh", "laughs": "laugh", "laughing": "laugh", "lol": "laugh",
    "chuckle": "chuckle", "chuckles": "chuckle", "chuckling": "chuckle", "giggle": "chuckle", "giggles": "chuckle",
    "sigh": "sigh", "sighs": "sigh", "sighing": "sigh", "exhale": "sigh", "exhales": "sigh",
    "clear throat": "clear throat", "clears throat": "clear throat", "ahem": "clear throat",
    "gasp": "gasp", "gasps": "gasp",
    "groan": "groan", "groans": "groan",
    "sniff": "sniff", "sniffs": "sniff", "sniffle": "sniff", "sniffles": "sniff",
    "cough": "cough", "coughs": "cough",
    "shush": "shush",
}
ENGINE_TAGS = sorted(set(CANON.values()))
_TAG = re.compile(r"\[\s*([a-zA-Z ]{3,14})\s*\]")
_LETTERS = "abcdefghijklmnopqrstuvwxyz"   # placeholders are plain lowercase words so every text pass leaves them alone


def normalize(text: str) -> str:
    """Bring every bracket tag to its engine form; unknown bracket content is removed."""
    def rep(m):
        key = " ".join(m.group(1).lower().split())
        return f"[{CANON[key]}]" if key in CANON else ""
    return _TAG.sub(rep, text)


def strip(text: str) -> str:
    """Remove all tags (for captions and for engines that cannot perform them)."""
    return " ".join(_TAG.sub("", text).split())


def protect(text: str) -> tuple[str, list[str]]:
    """Replace tags with placeholders so other text passes cannot mangle them; returns (text, tags)."""
    tags: list[str] = []

    def rep(m):
        key = " ".join(m.group(1).lower().split())
        if key not in CANON:
            return ""
        tags.append(CANON[key])
        if len(tags) > len(_LETTERS):
            return ""
        return f" xqtag{_LETTERS[len(tags) - 1]}qx "
    return _TAG.sub(rep, text), tags


def restore(text: str, tags: list[str]) -> str:
    def rep(m):
        i = _LETTERS.index(m.group(1))
        return f"[{tags[i]}]" if 0 <= i < len(tags) else ""
    out = re.sub(r"xqtag([a-z])qx", rep, text)
    return " ".join(out.split())


def has_tags(text: str) -> bool:
    return bool(_TAG.search(text))
