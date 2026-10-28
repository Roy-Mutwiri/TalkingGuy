"""LLM-free lesson builder used when there is no API key (offline mode) or the API fails.

It follows Theo's lesson arc (teaching.md): hook, plain words + analogy, point at it on the live chart,
the story, what confirms it and where it is wrong, the mistake, a check question to the chat, recap.
It still uses real market data: a genuine example of the lesson's pattern on the chart of the hour
(gold while forex is open, Bitcoin otherwise), with narration drawn from banks that never repeat back to back.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone

from ..data import patterns
from ..data.market_hours import primary_symbol
from ..data.service import DataService, DEFAULT_SYMBOLS, ExampleWindow
from ..data.sources import pretty_symbol
from .curriculum import Curriculum, Lesson
from .phrases import Picker
from .schema import Beat, HighlightAction, HLineAction, LessonScript, LoadAction, MarkerAction, Quiz, ZoomAction
from .teaching import notes_for, signpost

TF_WORDS = {"1m": "one minute", "5m": "five minute", "15m": "fifteen minute", "1h": "one hour", "4h": "four hour", "1d": "daily"}
MARKET_WORDS = {"XAU/USD": "gold", "BTC/USD": "Bitcoin", "ETH/USD": "Ethereum", "SOL/USD": "Solana", "EUR/USD": "euro dollar", "GBP/USD": "pound dollar"}

POINT_LEADS = ["First thing.", "Here's the core of it.", "Now the part people skip.", "Keep this in mind.", "Simple rule.",
               "Watch this.", "This is where it gets practical.", "One more layer.", "And the detail that matters:", "Quick one."]
EXAMPLE_LEADS = [
    "Right here, a {label}, {date}. Look at where it printed before you look at the shape.",
    "See this bar? {date}. That's a {label}. The shape is nice; the location is the lesson.",
    "There it is, {date}: a {label}. Now ask the only question that matters: what's behind it?",
    "On {date} price prints a {label}. Shape second. Location first.",
]
INVALIDATION_LEADS = [
    "The level that matters is around {price}. Through there, the idea is just wrong. Knowing that before you act is the whole point.",
    "Mark {price}. If price trades through it, the story is over and you stop arguing with the chart. That's your invalidation.",
    "Where's the line in the sand? About {price}. Beyond it, no opinions, no hoping. The idea failed, and that's information.",
]
LEVEL_LEADS = [
    "There's also a {label} near {price}; price touched it {touches} times in this window. Levels that get tested repeatedly are where reactions happen.",
    "Notice the {label} around {price}, tested {touches} times. Repeated touches mean the market remembers that price.",
]
LIVE_LEADS = [
    "This is the live chart. The last candle is still printing while we talk, so everything you see is real.",
    "Live chart, live candle on the right. Nothing here is a drawing.",
    "Everything on this chart is happening now; the right edge is the bar in progress.",
]
WATCH = ["the next test of that level", "whether the last candle closes beyond the level", "the first pullback after the move", "how price treats the invalidation line"]


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _spoken(p: float) -> str:
    if p >= 10000:
        return f"{round(p, -1):,.0f}"
    if p >= 100:
        return f"{p:,.0f}"
    return f"{p:.2f}" if p >= 1 else f"{p:.4f}"


def _spoken_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%B %d").replace(" 0", " ")


def _key_points(lesson: Lesson) -> list[str]:
    m = re.search(r"key points\s*:\s*(.+?)(?=\n- |\Z)", lesson.body, re.S | re.I)
    text = " ".join(m.group(1).split()) if m else lesson.title
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return sents[:5]


def _mistake(lesson: Lesson) -> str:
    m = re.search(r"common mistakes\s*:\s*(.+?)(?=\n- |\Z)", lesson.body, re.S | re.I)
    return " ".join(m.group(1).split()) if m else ""


class TemplatePlanner:
    def __init__(self, data: DataService, picker: Picker | None = None) -> None:
        self.data = data
        self.picker = picker or Picker()
        self.rng = random.Random()

    async def _window(self, lesson: Lesson) -> ExampleWindow | None:
        primary = primary_symbol()
        symbols = [primary]      # gold non-stop while forex is open, Bitcoin otherwise; a plain window beats switching markets
        wins = []
        if lesson.scanner != "none":
            wins = await self.data.find_examples(lesson.scanner, symbols[:1], lesson.tf)
            if not wins:
                wins = await self.data.find_examples(lesson.scanner, symbols[:1], "1h")
        if not wins:
            for s in symbols:
                try:
                    wins = [await self.data.plain_window(s, lesson.tf)]
                    break
                except Exception:  # noqa: BLE001
                    continue
        return wins[0] if wins else None

    def build(self, lesson: Lesson, w: ExampleWindow) -> LessonScript:
        """The arc, as beats, from a real example window (pure; tested without data)."""
        rng = self.rng
        name = pretty_symbol(w.symbol)
        market = MARKET_WORDS.get(name, name)
        tfn = TF_WORDS.get(w.tf, w.tf)
        topic = lesson.title.lower()
        notes = notes_for(lesson.title, lesson.body)
        pts = _key_points(lesson)
        beats: list[Beat] = []

        # 1 hook + load the live chart
        beats.append(Beat(say=f"{signpost('hook', rng, topic=topic)} {rng.choice(LIVE_LEADS)} {market}, {tfn} chart.",
                          chart=[LoadAction(symbol=w.symbol, tf=w.tf, start=_iso(w.start), end=_iso(w.end), replay=True, pace_ms=80)]))
        # 2 plain words, then the analogy
        beats.append(Beat(say=signpost("plain", rng, plain=notes.plain), pause_ms=500))
        beats.append(Beat(say=signpost("analogy", rng, analogy=notes.analogy), pause_ms=600))
        # 3 point at it on the chart (the real example when the scanner found one)
        inv = None
        if w.label != "recent price action":
            bull = any(k in w.label for k in ("bull", "support", "up", "golden", "oversold", "low"))
            step = (w.end - w.start) // max(1, len(w.candles))
            acts = [MarkerAction(time=_iso(w.hit_time), text=w.label[:20], position="belowBar" if bull else "aboveBar", shape="arrowUp" if bull else "arrowDown"),
                    HighlightAction(start=_iso(w.hit_time - 2 * step), end=_iso(w.hit_time + step), label=w.label[:20])]
            beats.append(Beat(say=signpost("point", rng, chart=rng.choice(EXAMPLE_LEADS).format(label=w.label, date=_spoken_date(w.hit_time))), chart=acts))
            inv = w.extra.get("invalidation") or w.extra.get("price") or w.extra.get("level")
        else:
            lv = patterns.levels(w.candles)
            if lv:
                l0 = lv[0]
                beats.append(Beat(say=signpost("point", rng, chart=rng.choice(LEVEL_LEADS).format(label=l0.label, price=_spoken(l0.extra["price"]), touches=l0.extra["touches"])),
                                  chart=[HLineAction(price=float(l0.extra["price"]), label=l0.label[:20], color="#2962ff")]))
                inv = l0.extra["price"]
            else:
                beats.append(Beat(say=signpost("point", rng, chart="Look at the last swing high and the last swing low. Everything in this lesson happens between those two prices.")))
        # 4 the story, with one key point from the curriculum folded in
        story = notes.story + (f" {rng.choice(POINT_LEADS)} {pts[0]}" if pts else "")
        beats.append(Beat(say=signpost("story", rng, story=story), pause_ms=500))
        # 5 confirm, then the invalidation line on the chart
        beats.append(Beat(say=signpost("confirm", rng, confirm=notes.confirm)))
        if inv:
            beats.append(Beat(say=rng.choice(INVALIDATION_LEADS).format(price=_spoken(float(inv))),
                              chart=[HLineAction(price=float(inv), label="Invalidation", color="#f23645", style="dotted")], pause_ms=500))
        else:
            beats.append(Beat(say="Where is it wrong? Beyond the level that gave you the reason. If price trades through it, the story is over.", pause_ms=500))
        # 6 the mistake (curriculum's own note first, library contrast second)
        mistake = _mistake(lesson) or notes.mistake
        beats.append(Beat(say=signpost("mistake", rng, mistake=mistake), pause_ms=400))
        if len(pts) > 1:
            beats.append(Beat(say=f"{rng.choice(POINT_LEADS)} {pts[1]}", pause_ms=300))
        # 7 the check: one answerable question to the chat (the director opens the answer window)
        beats.append(Beat(say=signpost("bridge", rng, topic=topic), ask=notes.check, pause_ms=200))
        # 8 recap in one breath
        takeaway = lesson.takeaway or (pts[0] if pts else lesson.title)
        if not takeaway.endswith((".", "!", "?")):
            takeaway += "."
        inv_text = f"through {_spoken(float(inv))}" if inv else "through the level behind the idea"
        beats.append(Beat(say=signpost("recap", rng, takeaway=takeaway, invalidation=inv_text, watch=rng.choice(WATCH)),
                          chart=[ZoomAction(start=_iso(w.start + (w.end - w.start) // 3), end=_iso(w.end))], pause_ms=800))
        quiz = Quiz(question=notes.check, answer=f"{notes.confirm} And if price trades {inv_text}, the idea is wrong and you stop reasoning about it.")
        return LessonScript(topic=lesson.title, module=lesson.module, summary=lesson.takeaway or lesson.title, beats=beats, quiz=quiz)

    async def plan(self, lesson: Lesson) -> LessonScript:
        w = await self._window(lesson)
        if w is None:
            raise RuntimeError("no data for template lesson")
        return self.build(lesson, w)

    async def plan_topic(self, curriculum: Curriculum, text: str) -> LessonScript:
        lesson = curriculum.find(text) or random.choice(curriculum.lessons)
        return await self.plan(lesson)
