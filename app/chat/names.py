"""Turn TikTok display names and handles into something a host can say out loud.

  "maria_fx_2024"   -> "Maria"
  "kev99"           -> "Kev"
  "🔥Ali Gold🔥"     -> "Ali"
  "xX_D4rk_Xx"      -> "Dark"  (leet-speak unfolded when it yields a known name)
  "user8812937"     -> "" (no speakable name -> the host says "friend" instead)

Backed by the Global-Human-Names dataset (first names from many countries) when
`data_cache/names.json` has been built (scripts/build_names.py), with a safe regex fallback.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_NAMES: set[str] | None = None
_PATH = Path("data_cache/names.json")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_SYMBOLS = re.compile(r"[^\w\s]", re.UNICODE)
_SPLIT = re.compile(r"[\s_.\-]+|(?<=[a-z])(?=[A-Z])")
FALLBACKS = ["friend", "my friend", "chief", "boss"]


def _load() -> set[str]:
    global _NAMES
    if _NAMES is None:
        try:
            _NAMES = set(json.loads(_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            _NAMES = set()
    return _NAMES


def speakable_name(display: str, fallback: str = "friend") -> str:
    """Best effort first name to say on air; `fallback` when nothing is pronounceable."""
    if not display:
        return fallback
    names = _load()
    s = _SYMBOLS.sub(" ", display)          # drop emoji and punctuation
    parts = [p for p in _SPLIT.split(s) if p]
    ok = lambda w: w.isalpha() and 3 <= len(w) <= 14 and w.lower() not in GENERIC and re.search(r"[aeiouy]", w, re.I)  # noqa: E731
    # 1) a known first name among the parts (letters only)
    for p in parts:
        w = re.sub(r"\d+$", "", p)          # kev99 -> kev
        if ok(w) and (not names or w.lower() in names):
            return w[:1].upper() + w[1:].lower()
    # 2) leet-speak unfolding
    for p in parts:
        w = re.sub(r"\d+$", "", p.translate(_LEET))
        if ok(w) and names and w.lower() in names:
            return w[:1].upper() + w[1:].lower()
    # 3) any alphabetic word that looks like a name
    for p in parts:
        w = re.sub(r"\d+$", "", p)
        if ok(w) and len(w) <= 12:
            return w[:1].upper() + w[1:].lower()
    return fallback


GENERIC = {"user", "official", "trader", "trading", "trades", "crypto", "forex", "gold", "the", "real", "its", "mr", "mrs", "miss", "king", "queen",
           "boss", "big", "lil", "little", "young", "old", "money", "cash", "rich", "pro", "fx", "btc", "eth", "live", "tiktok", "official",
           "investor", "invest", "signals", "signal", "profit", "guru", "capital", "markets", "market", "xxx", "www", "com", "page", "fan", "fans"}


def strip_for_speech(text: str) -> str:
    """Remove emoji/pictographs/dingbats and decorative symbols so TTS never reads them."""
    return _EMOJI.sub("", text)


_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # emoticons, symbols, pictographs, transport, flags, supplemental
    "\U00002600-\U000027BF"   # misc symbols, dingbats
    "\U00002B00-\U00002BFF"   # arrows & misc
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0001F1E6-\U0001F1FF"   # regional indicators
    "\U000E0020-\U000E007F"   # tags
    "‍⃣™ℹ↔-↪⌚-⏿Ⓜ▪-◾⤴⤵〰〽㊗㊙"
    "]+",
    flags=re.UNICODE,
)
