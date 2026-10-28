"""Decides which chat comments deserve an on-air answer."""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field

_BAD = re.compile(r"\b(fuck|shit|bitch|nigg|porn|sex|nude|kill yourself|kys)\w*", re.I)
_SPAM = re.compile(r"(https?://|www\.|\.com\b|t\.me/|telegram|whatsapp|discord\.gg|dm me|follow me|follow back|f4f|promo|giveaway)", re.I)
_LOW_VALUE = re.compile(r"^\W*(hi+|hello+|hey+|lol+|wow+|nice|cool|ok+|first|good|great|👍|❤️|🔥)+\W*$", re.I)
_QUESTION_HINTS = re.compile(r"(\?|\bwhat\b|\bwhy\b|\bhow\b|\bwhen\b|\bwhich\b|\bis it\b|\bdo you\b|\bcan you\b|\bshould\b|\bexplain\b|\bmean\b)", re.I)
_TRADING_WORDS = re.compile(r"(chart|candle|trend|support|resistance|level|pattern|indicator|rsi|macd|volume|risk|stop|entry|breakout|pullback|liquidity|order|bitcoin|btc|eth|forex|stock|gold|crypto|trade|trading|invest|bull|bear|wick|engulf|doji|fib|ema|sma|timeframe|range|market|price|ai|bot|real|human)", re.I)


@dataclass
class Question:
    user: str
    text: str
    score: float
    ts: float = field(default_factory=time.time)


class Moderator:
    def __init__(self, per_user_cooldown_s: int = 120, max_len: int = 240) -> None:
        self.cooldown = per_user_cooldown_s
        self.max_len = max_len
        self.last_by_user: dict[str, float] = {}
        self.recent_texts: deque[str] = deque(maxlen=50)

    def assess(self, user: str, text: str) -> Question | None:
        t = " ".join((text or "").split())
        if not t or len(t) > self.max_len or len(t) < 6:
            return None
        if _BAD.search(t) or _SPAM.search(t) or _LOW_VALUE.match(t):
            return None
        key = t.lower()
        if key in self.recent_texts:
            return None
        now = time.time()
        if now - self.last_by_user.get(user, 0) < self.cooldown:
            return None
        score = 0.0
        if _QUESTION_HINTS.search(t):
            score += 2
        score += min(3, len(_TRADING_WORDS.findall(t)))
        if score < 2:
            return None
        self.recent_texts.append(key)
        self.last_by_user[user] = now
        return Question(user=user, text=t, score=score)
