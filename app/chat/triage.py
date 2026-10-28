"""Comment triage: decide, like a human host would, which comments deserve an answer now,
which can wait, which get a nod when idle, and which are spam to ignore. Also extracts a
lesson topic when a viewer is asking to learn something.

Uses Claude in batches (one structured call per ~4 s of chat) when a client is available,
otherwise a heuristic that is deliberately conservative.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

log = logging.getLogger("chat")

Priority = Literal["high", "medium", "low", "spam"]
RANK = {"high": 0, "medium": 1, "low": 2, "spam": 9}


class TriageItem(BaseModel):
    idx: int
    priority: Priority
    topic: str | None = Field(default=None, description="3-6 word lesson topic if the viewer wants to learn something, else null")
    reply_hint: str | None = Field(default=None, description="optional 1-line note on how a human host would handle it")


class TriageBatch(BaseModel):
    items: list[TriageItem]


TRIAGE_RULES = """You are the chat producer for a live trading classroom hosted by Theo (an AI teacher).
Classify each chat comment the way a sharp human host would, and extract a lesson topic when the viewer is asking to learn something.

high   = a real question about trading, charts, the current lesson, risk, psychology, or a direct question to the host;
         a regular viewer returning with a follow-up; a correction or a sharp observation worth engaging.
medium = an on-topic remark, a greeting that names the host, a short reaction that deserves one friendly line,
         a question that is vague but answerable in one sentence.
low    = generic chatter: "hi", "nice", emojis only, "first", "W", one-word reactions. A human host nods at these only when idle.
spam   = promotions, links, handles, "dm me", signal groups, "I made $X with Y", referral codes, repeated/bot text,
         hate or harassment, requests for the host to buy/sell for them, anything off-platform.

topic: when a comment asks to learn or explain something (e.g. "can you explain fibonacci", "what is a stop hunt",
"how do I size a position"), write a short lesson topic in 3-6 words. Otherwise null.

Return one item per comment, in the same order, with the same idx.
"""


class Triager:
    def __init__(self, client=None, persona: str = "") -> None:
        self.client = client
        self.persona = persona
        self.spam_seen = 0

    # ------------------------------------------------------------------ heuristic
    _Q = re.compile(r"(\?|\bwhat\b|\bwhy\b|\bhow\b|\bwhen\b|\bwhich\b|\bexplain\b|\bcan you\b|\bshould\b|\bmean\b)", re.I)
    _TRADE = re.compile(r"(chart|candle|trend|support|resistance|level|pattern|indicator|rsi|macd|ema|sma|fib|volume|risk|stop|entry|breakout|pullback|liquidity|order|gold|xau|btc|bitcoin|eth|forex|stock|crypto|trade|trading|bull|bear|wick|engulf|doji|range|market|price|timeframe|position|lot|leverage|psychology|loss)", re.I)
    _LEARN = re.compile(r"(explain|teach|how (do|to|can) (i|you|we)|what is|what's|whats|can you (show|cover|do)|lesson on|talk about)\s+(.{3,60})", re.I)
    _GREET = re.compile(r"\b(theo|hi|hello|hey|good (morning|evening|night))\b", re.I)

    def heuristic(self, texts: list[str]) -> list[TriageItem]:
        out = []
        for i, t in enumerate(texts):
            words = len(self._TRADE.findall(t))
            q = bool(self._Q.search(t))
            topic = None
            m = self._LEARN.search(t)
            if m:
                topic = " ".join(m.group(m.lastindex).split()[:6]).strip(" ?.!")
            if q and words >= 1 and len(t) > 12:
                pr = "high"
            elif words >= 1 or (self._GREET.search(t) and len(t) > 8) or (q and len(t) > 15):
                pr = "medium"
            else:
                pr = "low"
            out.append(TriageItem(idx=i, priority=pr, topic=topic))
        return out

    # ------------------------------------------------------------------ Claude
    async def classify(self, comments: list[tuple[str, str]]) -> list[TriageItem]:
        """comments: list of (user, text). Returns items aligned by idx."""
        texts = [t for _, t in comments]
        if self.client is None or not comments:
            return self.heuristic(texts)
        from ..brain.client import CHAT_MODEL, structured

        lines = "\n".join(f"{i}. @{u}: {t[:240]}" for i, (u, t) in enumerate(comments))
        try:
            batch = await asyncio.to_thread(
                structured, self.client, TriageBatch, system=self.persona + "\n" + TRIAGE_RULES,
                user=f"COMMENTS:\n{lines}\n\nClassify every comment.", effort="low", max_tokens=2500, model=CHAT_MODEL,
            )
            by_idx = {it.idx: it for it in batch.items}
            items = [by_idx.get(i) or TriageItem(idx=i, priority="low") for i in range(len(comments))]
        except Exception as exc:  # noqa: BLE001
            log.warning("triage via model failed (%s); heuristic", exc)
            items = self.heuristic(texts)
        self.spam_seen += sum(1 for it in items if it.priority == "spam")
        return items
