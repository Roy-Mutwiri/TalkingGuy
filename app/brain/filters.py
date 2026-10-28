"""Compliance post-filter for anything the teacher says on air.

TikTok's financial-content rules and plain honesty forbid: trade signals, price
predictions/targets, guaranteed or income claims, and pushing people to DMs/links.
The system prompt already tells the model this; the filter is the seatbelt.
"""
from __future__ import annotations

import re

RULES: list[tuple[str, re.Pattern]] = [
    ("signal", re.compile(r"\b(buy|sell|long|short|enter|go long|go short)\b[^.!?]{0,30}\b(now|today|here|immediately|right now)\b", re.I)),
    ("signal", re.compile(r"\b(entry|entries|take profit|tp|stop loss|sl)\s*(at|:|=)\s*\$?\d", re.I)),
    ("signal", re.compile(r"\b(my|our|this)\s+(signal|signals|call|calls|setup to take)\b", re.I)),
    ("prediction", re.compile(r"\b(will|is going to|gonna|guaranteed to|bound to|about to)\s+(go|hit|reach|pump|dump|moon|crash|rally|drop|break)\b", re.I)),
    ("prediction", re.compile(r"\b(price target|target of|targets?\s+\$?\d|will be at \$?\d|hits? \$?\d[\d,]*\s*(soon|by|this))", re.I)),
    ("prediction", re.compile(r"\b(i predict|my prediction|next (week|month) (it|price|btc|bitcoin) (will|is going))", re.I)),
    ("guarantee", re.compile(r"\b(guarantee[ds]?|risk[- ]free|can'?t lose|cannot lose|never loses|100% (win|sure|certain|accurate))\b", re.I)),
    ("income", re.compile(r"\b(make|earn|made|earned)\s+\$?\d[\d,]*\s*(a|per|each|every)?\s*(day|week|month|year)\b", re.I)),
    ("income", re.compile(r"\b(get rich|passive income|quit your job|financial freedom in)\b", re.I)),
    ("solicitation", re.compile(r"\b(dm me|message me|join my|my telegram|my discord|whatsapp|link in (my )?bio|sign ?up (link|here)|use my code|referral)\b", re.I)),
    ("advice", re.compile(r"\b(you should (buy|sell|invest in|put your money)|i recommend (buying|selling|investing))\b", re.I)),
]

_SENT = re.compile(r"(?<=[.!?])\s+")


def violations(text: str) -> list[tuple[str, str]]:
    """Return (rule, offending sentence) pairs."""
    found = []
    for sent in _SENT.split(text or ""):
        for rule, rx in RULES:
            if rx.search(sent):
                found.append((rule, sent.strip()))
                break
    return found


def sanitize(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Drop offending sentences. Returns (clean_text, violations)."""
    bad = violations(text)
    if not bad:
        return text, []
    bad_sentences = {s for _, s in bad}
    kept = [s for s in _SENT.split(text) if s.strip() not in bad_sentences]
    return " ".join(kept).strip(), bad


DISCLAIMER_LINES = [
    "Quick reminder: this is education, not financial advice. I teach, you decide.",
    "Nothing here is a signal. I show you how to read a chart, you decide what to do with your own risk.",
    "I never know where price goes next. Nobody does. We work with levels and invalidation, not predictions.",
]
