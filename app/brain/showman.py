"""The showman layer: what keeps a TikTok LIVE audience from scrolling.

Everything here is grounded in real events (real price moves, real joins, real likes, real
viewer counts) and stays inside the compliance lines (excitement about the chart and the
room, never about money). The director calls these between beats; the stage gets a visual
flash immediately so the energy is on screen even while Theo is mid-sentence.
"""
from __future__ import annotations

import math
import os
import random
import time
from collections import deque
from dataclasses import dataclass

ENERGY = max(0.0, min(1.0, float(os.getenv("ENERGY", "0.85") or 0.85)))

# how big a move (in % within ~60 s) earns a live reaction, per instrument family
MOVE_THRESHOLDS = {"XAU/USD": 0.12, "BTC/USD": 0.35, "ETH/USD": 0.45, "SOL/USD": 0.6, "EUR/USD": 0.06, "GBP/USD": 0.07, "USD/JPY": 0.07, "PAXG/USD": 0.12}
REACTION_COOLDOWN_S = 150.0
HOT_EVENT_TTL_S = 90.0

HOOK_EVERY_S = 90.0 if ENERGY >= 0.7 else 150.0
WELCOME_EVERY_S = 20.0 if ENERGY >= 0.7 else 60.0


@dataclass
class HotMove:
    symbol: str
    pct: float          # signed % move over the window
    price: float
    ts: float

    @property
    def direction(self) -> str:
        return "up" if self.pct > 0 else "down"


class MoveDetector:
    """Rolling 60-second window per symbol; fires once per cooldown when a real move exceeds the threshold."""

    def __init__(self, window_s: float = 60.0) -> None:
        self.window_s = window_s
        self.hist: dict[str, deque[tuple[float, float]]] = {}
        self.last_fired: dict[str, float] = {}

    def feed(self, symbol: str, price: float, ts: float | None = None) -> HotMove | None:
        ts = ts or time.time()
        d = self.hist.setdefault(symbol, deque())
        d.append((ts, price))
        while d and ts - d[0][0] > self.window_s:
            d.popleft()
        if len(d) < 3 or ts - self.last_fired.get(symbol, 0) < REACTION_COOLDOWN_S:
            return None
        ref = d[0][1]
        if not ref:
            return None
        pct = (price - ref) / ref * 100
        if abs(pct) >= MOVE_THRESHOLDS.get(symbol, 0.3):
            self.last_fired[symbol] = ts
            return HotMove(symbol, round(pct, 2), price, ts)
        return None


def spoken_symbol(symbol: str) -> str:
    return {"XAU/USD": "gold", "BTC/USD": "Bitcoin", "ETH/USD": "Ethereum", "SOL/USD": "Solana", "EUR/USD": "euro dollar", "GBP/USD": "cable", "USD/JPY": "dollar yen", "PAXG/USD": "Pax gold"}.get(symbol, symbol)


def fmt_price(p: float) -> str:
    return f"{p:,.1f}" if p >= 1000 else f"{p:.2f}" if p >= 10 else f"{p:.4f}"


REACTIONS = [
    "[gasp] Whoa, {sym} just moved {pct} percent in about a minute, {dir} to {price}. Eyes on the chart, this is the part you learn from.",
    "[laugh] Okay okay, look at this! {sym} {dir} {pct} percent in a minute, now {price}. Watch how it treats the last level we marked.",
    "Hold on. {sym} just ripped {dir}, {pct} percent, {price} right now. No predictions, but this is exactly when the levels matter.",
    "[gasp] There it is! {sym} {pct} percent {dir} in sixty seconds, sitting at {price}. Chat, is it holding the level or not? Type H or N.",
    "Live one: {sym} pushed {dir} {pct} percent, {price} now. This is why we mark levels before the move, not after.",
]

WELCOME_FAST = [
    "{names}, welcome in! Perfect timing.",
    "Hey {names}! Grab a seat, we're on {topic}.",
    "{names} just landed. Welcome, you're right on time for {topic}.",
    "Welcome {names}! Say hi in the chat, I read everything.",
    "Oh nice, {names} is here. Welcome to the chart room.",
    "{names}, welcome! Quick version: {topic}. Stay for the next two minutes, it pays off.",
    "Big welcome to {names}. You picked a good moment.",
    "{names}! Good to have you. We're deep in {topic} right now.",
]

LIKE_GOAL = [
    "We're at {likes} likes, let's push it to {target}! Tap the screen, it genuinely helps the stream reach more people.",
    "{likes} likes already, {target} is the goal. Double tap if this is helping.",
    "Chat, {likes} likes! Can we hit {target} before the next lesson? I think we can.",
    "Love this. {likes} likes. {target} and I'll do the mistake-of-the-day story early.",
]
LIKE_HIT = [
    "We hit {target} likes! Thank you, that's huge. Next goal: {next_target}.",
    "{target} likes, done! You lot are the best chart room on TikTok. New goal: {next_target}.",
    "Boom, {target} likes. Appreciate every tap. Let's go for {next_target}.",
]
VIEWERS_MILESTONE = [
    "{viewers} of you in here right now. Welcome everyone, this is the chart room.",
    "Look at that, {viewers} people watching. If you're new: {topic}, and I read every comment.",
    "{viewers} in the room! Say where you're watching from, I love that.",
]
CLIFFHANGER = [
    "Stay for the next one: {tease}. That's the part that costs beginners the most.",
    "Don't scroll yet. Coming up: {tease}.",
    "Next up, and this is my favourite bit: {tease}.",
    "Give me two more minutes. {tease}, and then you'll never unsee it.",
    "After this: {tease}. Keep the chat going, I'm reading.",
]
GIFT_HYPE = [
    "{name} sent {gift}! Thank you, that's awesome. Seriously, appreciate you.",
    "Oh, {gift} from {name}! Thank you so much, welcome to the front row.",
    "{name}, {gift}, you legend. Thank you!",
]
SHARE_HYPE = [
    "{name} just shared the stream. Thank you! Shares are how new people find the room.",
    "Shout out to {name} for sharing. That's how we grow this, thank you.",
]
HYPE_OPENERS = ["Okay!", "Let's go.", "Right.", "Here we go.", "Okay, chat."]


def pick(bank: list[str], recent: list[str], **fmt) -> str:
    """Random line not used in the last few picks of this bank."""
    pool = [b for b in bank if b not in recent[-4:]] or bank
    line = random.choice(pool)
    recent.append(line)
    del recent[:-12]
    try:
        return line.format(**fmt)
    except (KeyError, IndexError):
        return line


def next_like_target(likes: int) -> int:
    """The next round goal above the current count: 100, 250, 500, 1k, 2.5k, 5k, 10k ..."""
    ladder = [100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
    for t in ladder:
        if likes < t:
            return t
    return int(math.ceil(likes / 50000.0) * 50000) + 50000


def energize(text: str, mood: str | None) -> str:
    """Punchier delivery for show moods: short openers become exclamations, flat enders get lift.
    Light touch, never inside numbers, never on serious lines."""
    if ENERGY < 0.7 or mood in (None, "serious", "calm", "considerate"):
        return text
    parts = [p for p in text.replace("! ", "!\n").replace(". ", ".\n").split("\n") if p.strip()]
    out = []
    for i, p in enumerate(parts):
        s = p.strip()
        words = s.split()
        if i == 0 and len(words) <= 3 and s.endswith(".") and not any(ch.isdigit() for ch in s):
            s = s[:-1] + "!"
        out.append(s)
    return " ".join(out)
