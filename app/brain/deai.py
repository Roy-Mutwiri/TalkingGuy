"""Scrub AI-writing tells out of anything Haddan says.

Based on Wikipedia's "Signs of AI writing" (vocabulary, copula avoidance, negative parallelism, summary
endings, sycophantic openers, chatbot artifacts, em dashes) plus the usual LLM marketing vocabulary.
Applied to every utterance before speech, to brain output before it is stored in memory, and used by
scripts/ai_tells_audit.py to measure how often the brain still slips.

Replacement is conservative: trading terms stay (leverage as a noun, key level, highlight on a chart
means a drawing). Sentences that are pure chatbot artifacts are dropped whole.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENT = re.compile(r"(?<=[.!?])\s+")

# word-level: tell -> plain spoken English (case-insensitive, whole words)
WORDS: dict[str, str] = {
    r"delve into": "dig into", r"delves into": "digs into", r"delving into": "digging into", r"delve": "dig in",
    r"a deep dive": "a close look", r"deep dive": "close look", r"let'?s dive in": "let's get into it", r"dive into": "get into",
    r"tapestry": "mix", r"testament to": "sign of", r"a testament": "a sign",
    r"crucial": "important", r"pivotal": "big", r"vital": "important", r"paramount": "the big one",
    r"underscores": "shows", r"underscore": "show", r"underscoring": "showing", r"emphasizes": "shows", r"emphasizing": "showing",
    r"highlights the importance of": "shows why you need", r"highlighting the importance of": "showing why you need",
    r"landscape": "market", r"vibrant": "busy", r"robust": "solid", r"seamless(?:ly)?": "smooth",
    r"utilize": "use", r"utilizing": "using", r"utilise": "use",
    r"fostering": "building", r"fosters": "builds", r"foster": "build",
    r"showcases": "shows", r"showcase": "show", r"showcasing": "showing",
    r"enhances": "improves", r"enhance": "improve", r"enhancing": "improving",
    r"navigate the": "handle the", r"navigating the": "handling the",
    r"trading journey": "trading", r"your journey": "your trading", r"embark on": "start", r"embarking on": "starting",
    r"unlock": "open up", r"game.?changer": "big deal", r"realm": "area", r"elevate": "lift", r"empower(?:s|ing)?": "help",
    r"intricate": "detailed", r"intricacies": "details", r"meticulously": "carefully", r"meticulous": "careful", r"interplay": "back and forth",
    r"boasts": "has", r"boasting": "with", r"garner(?:s|ed)?": "get", r"bolstered": "helped", r"enduring": "lasting",
    r"additionally,?": "also,", r"furthermore,?": "and", r"moreover,?": "and", r"consequently,?": "so",
    r"in today'?s (?:fast-paced|digital|modern) (?:world|age|markets?)": "today", r"in the world of trading": "in trading",
    r"valuable insights?": "useful points", r"ensure that": "make sure", r"ensures that": "makes sure", r"ensure": "make sure",
    r"serves as": "is", r"stands as": "is", r"functions as": "is", r"operates as": "is", r"represents a": "is a", r"refers to": "means",
    r"it'?s important to note that": "", r"it'?s worth noting that": "", r"it'?s worth mentioning that": "", r"keep in mind that": "",
    r"it should be noted that": "", r"needless to say,?": "", r"at the end of the day,?": "", r"that being said,?": "still,",
    r"in conclusion,?": "", r"in summary,?": "", r"to sum up,?": "", r"all in all,?": "", r"ultimately,?": "",
    r"whether you'?re (?:a )?(?:beginner|new|seasoned|experienced)[^.,!?]*,?": "",
    r"a wide range of": "lots of", r"a variety of": "different", r"a plethora of": "plenty of", r"a myriad of": "lots of",
    r"in order to": "to", r"due to the fact that": "because", r"with respect to": "about", r"in terms of": "for",
    r"cutting-edge": "new", r"state-of-the-art": "new", r"groundbreaking": "big", r"revolutionary": "big", r"holistic": "whole",
    r"synerg(?:y|ies|istic)": "fit", r"streamline": "simplify", r"optimal": "best", r"facilitate": "help",
}
_WORD_RX = [(re.compile(r"\b" + k + r"\b", re.I), v) for k, v in WORDS.items()]

# whole sentences that are chatbot artifacts: dropped
DROP_SENTENCE = re.compile(
    r"\b(i hope (this|that) helps|let me know if|feel free to|as an ai language model|as an ai,|i'?m (just )?an ai language model|"
    r"i don'?t have (access to )?real-?time|my (knowledge|training) (cutoff|data)|happy to help|i'?m here to help|great question|excellent question|"
    r"fantastic question|wonderful question|certainly!|absolutely!|of course!|sure thing!|without further ado)\b", re.I)

# negative parallelism -> plain statement
_NOT_ONLY = re.compile(r"\bnot only (.+?),? but (?:also )?(.+?)([.!?]|$)", re.I)
_NOT_JUST = re.compile(r"\b(it'?s|this is|that'?s) not (?:(?:just|only|merely) (?:about )?|about )(.+?),? (?:it'?s|this is|that'?s) (?:about )?(.+?)([.!?]|$)", re.I)
_NOT_X_BUT_Y = re.compile(r"\bnot (?:a |an |the )?([^,.!?]{3,40}), but (?:a |an |the )?([^,.!?]{3,60})([.!?]|$)", re.I)


@dataclass
class Report:
    text: str
    fixes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.fixes)


def clean(text: str) -> Report:
    """Return the text with AI tells removed or rewritten, and the list of what was changed."""
    if not text:
        return Report(text)
    fixes: list[str] = []
    t = text
    # punctuation tells
    if "—" in t or "–" in t:
        t = re.sub(r"\s*[—–]\s*", ", ", t)
        fixes.append("em dash")
    if any(ch in t for ch in "“”‘’"):
        t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = re.sub(r"!{2,}", "!", t)
    # drop artifact sentences
    kept = []
    for s in _SENT.split(t):
        if DROP_SENTENCE.search(s):
            fixes.append("artifact: " + s.strip()[:40])
            continue
        kept.append(s)
    t = " ".join(kept)
    # parallelisms
    for rx, rep, label in ((_NOT_ONLY, r"\1 and \2\3", "not only/but also"), (_NOT_JUST, r"\1 \3\4", "not just X, it's Y"),
                           (_NOT_X_BUT_Y, r"\2\3", "not X, but Y")):
        if rx.search(t):
            t = rx.sub(rep, t)
            fixes.append(label)
    # vocabulary
    for rx, rep in _WORD_RX:
        if rx.search(t):
            fixes.append(rx.pattern.strip("\\b")[:24])
            t = rx.sub(rep, t)
    # tidy: double spaces, orphaned commas, capitalise sentence starts after removals
    t = re.sub(r"([.!?])\s*,\s*", r"\1 ", t)        # a dropped opener leaves ". , we" behind
    t = re.sub(r"^\s*,\s*", "", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    t = re.sub(r"(^|[.!?]\s+),\s*", r"\1", t)
    return Report(t, fixes)


def tells_in(text: str) -> list[str]:
    """Names of the tells present (for audits), without changing the text."""
    return clean(text).fixes


HUMAN_RULES = """WRITE LIKE A PERSON TALKING, NOT LIKE A MODEL (these are the known tells; never produce them):
- Banned words: delve, tapestry, testament, crucial, pivotal, vital, underscore, highlight (as a verb), landscape, vibrant, robust, seamless, utilize, foster, showcase, enhance, navigate, journey, embark, unlock, game-changer, realm, elevate, empower, intricate, meticulous, interplay, boasts, garner, bolster, enduring, additionally, furthermore, moreover, valuable insights, ensure.
- Say "is", not "serves as", "stands as", "represents", "refers to".
- No negative parallelism: never "not only X but also Y", never "it's not about X, it's about Y", never "no X, no Y, just Z".
- No groups of three for effect. One or two concrete things beat a neat triplet.
- No summary endings ("in conclusion", "in summary", "overall", "ultimately", "at the end of the day") and no filler ("it's important to note", "it's worth noting", "keep in mind that").
- No sycophancy or chatbot talk: never "great question", "certainly", "absolutely", "I hope this helps", "let me know", "as an AI language model". (Being asked directly whether you are an AI, you answer yes, plainly, once.)
- No em dashes, no curly quotes, no emojis, no headings, no bullet points.
- Hedge once if you must, not in stacks ("may potentially generally"). Prefer a specific number, name or candle over a generality.
- Vary sentence length. Use contractions. Have an opinion. Start sentences with "And" or "But" when a person would.
"""
