"""The Director: the state machine that keeps the stream alive and never idle.

    intro -> [lesson beats, answering chat between beats] -> Q&A block -> (every ~25 min) market tour
          -> small rituals (mistake of the day, honest "it's boring") -> next lesson ...

It talks to the stage through the hub's /ws/control socket, speaks through the Speaker,
pulls candles from DataService, lessons from the planner (pre-generated two ahead),
viewer questions from the ChatReader queue, and remembers everything through TeacherMemory.
Operator commands arrive on the same socket.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import websockets

from .brain.curriculum import Curriculum, Lesson
from .brain.phrases import Picker
from .brain.schema import convert_times, LessonScript, iso_to_unix
from .brain.template_planner import TemplatePlanner
from .brain.host_policy import DELIVERY_TO_MOOD, QUIET_INITIATIVE_S, STALE_REPLY_S, Comment, HostState, hint_for, is_duplicate, is_injection, reply_for
from .brain import showman
from .brain.client import brain_available, spend_summary
from .voice.nonverbal import NonVerbal
from .brain.deai import clean as deai_clean
from .brain.showman import ENERGY, HOOK_EVERY_S, WELCOME_EVERY_S, HOT_EVENT_TTL_S, MoveDetector, energize, fmt_price, next_like_target, spoken_symbol
from .chat.tiktok_reader import ChatReader
from .chat.triage import Triager
from .chat.names import speakable_name
from .data.market_hours import next_change, primary_symbol, session_name
from .data.service import DataService, WATCHLIST
from .data.sources import pretty_symbol
from .data.store import TF_SECONDS
from .voice.disfluency import Imperfections, humanize_text
from .brain.community import Community
from .voice.human import MURMURS
from .voice.pronounce import humanize
from .data.analysis import analyze

log = logging.getLogger("director")
HISTORY_PATH = Path("data_cache/lesson_history.json")
MARKET_TOUR_EVERY_S = 15 * 60
RITUAL_EVERY_S = 40 * 60
REPEAT_COOLDOWN_S = 72 * 3600


class Director:
    def __init__(self, hub_url: str, data: DataService, curriculum: Curriculum, planner, responder, speaker, chat: ChatReader,
                 offline: bool = False, memory=None, quotes=None, music=None) -> None:
        self.hub_url = hub_url
        self.data = data
        self.curriculum = curriculum
        self.planner = planner          # LessonPlanner (Claude) or None
        self.responder = responder      # ChatResponder (Claude) or None
        self.speaker = speaker          # a Speaker-like object or None (captions only)
        self.chat = chat
        self.memory = memory            # TeacherMemory or None
        self.quotes = quotes            # QuoteService or None
        self.music = music              # MusicBed or None
        self.last_hook = time.time()
        self.last_prompt = time.time() + 120
        self.last_welcome = time.time()
        self.last_thanks = 0.0
        self.pending_joins: list[str] = []
        self._last_loaded: list[dict] | None = None
        self.live_symbol: str | None = None     # pretty symbol whose live 1m candles feed the big chart
        self.chart_is_live = False
        self.triager = Triager(getattr(responder, "client", None))
        self.last_topic_from_chat = 0.0
        self._chat_was_connected = None
        self.offline = offline or planner is None
        self.picker = Picker()
        self.template = TemplatePlanner(data, self.picker)
        self.ws = None
        self.paused = False
        self.muted = False
        self.skip_beat = False
        self.skip_lesson = False
        self.force_market = False
        self.hot_alert = None            # {"label", "price", "direction", "at"} set by the stage when an alert line is crossed
        self.replay_done = asyncio.Event()
        self.lesson_queue: asyncio.Queue[LessonScript] = asyncio.Queue(maxsize=2)
        self.topic_requests: asyncio.Queue[str] = asyncio.Queue()
        self.recent_says: list[str] = []
        self.current_title = ""
        self.current_symbol: str | None = None
        self.last_market_tour = time.time()
        self.last_ritual = time.time()
        self.history: dict[str, float] = self._load_history()
        self.lessons_played = 0
        self.questions_answered = 0
        self._last_module: str | None = None
        self.promises: list[dict] = []                 # things Haddan said he would show/explain (delivered by deliver_promises)
        self.answered_texts: list[tuple[float, str]] = []   # (ts, question) for duplicate suppression
        self.pending_question: dict | None = None
        self.last_speech_end = time.time()
        self._initiatives = 0
        # showman layer: real moves, real likes, real viewers
        self.base_mood = "show" if ENERGY >= 0.7 else "teach"
        self.moves = MoveDetector()
        self.hot_events: list = []
        self.likes_total = 0
        self.like_target = next_like_target(0)
        self.last_like_call = 0.0
        self.viewers_announced = 0
        self._recent_lines: dict[str, list[str]] = {}
        self._music_base: float | None = None
        self.nonverbal = NonVerbal(energy=ENERGY)
        self.community = Community(self.picker, enabled=os.getenv("COMMUNITY_MENTIONS", "1") != "0")
        self.slips = Imperfections()
        self._interrupt_hot = None          # a big live move that arrived while a lesson line was being spoken
        self._last_interrupt = 0.0
        self._in_lesson_speech = False
        self._last_murmur = 0.0

    # ------------------------------------------------------------------ persistence
    def _load_history(self) -> dict[str, float]:
        try:
            return json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save_history(self) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps(self.history))

    def _segment(self, kind: str, topic: str, start: float, end: float) -> None:
        """Append a segment boundary for the clip cutter."""
        try:
            p = Path("data_cache/segments.jsonl")
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": kind, "topic": topic, "start": start, "end": end}) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def next_lesson(self) -> Lesson:
        """Oldest-played lesson first, never the same module twice in a row when avoidable."""
        now = time.time()
        candidates = [l for l in self.curriculum.lessons if now - self.history.get(l.key, 0) > REPEAT_COOLDOWN_S]
        if not candidates:
            candidates = list(self.curriculum.lessons)
        candidates.sort(key=lambda l: self.history.get(l.key, 0))
        pool = candidates[:10]
        other = [l for l in pool if l.module != self._last_module]
        return random.choice(other or pool)

    # ------------------------------------------------------------------ hub I/O
    @staticmethod
    def _valid_bar(c: dict) -> bool:
        try:
            return all(isinstance(c.get(k), (int, float)) and c.get(k) == c.get(k) for k in ("time", "open", "high", "low", "close"))
        except AttributeError:
            return False

    async def send(self, msg: dict) -> None:
        if self.ws:
            if msg.get("type") == "chart":
                # a single null OHLC value makes the chart library drop the whole series: never ship one
                if isinstance(msg.get("candles"), list):
                    msg["candles"] = [c for c in msg["candles"] if self._valid_bar(c)]
                if "candle" in msg and not self._valid_bar(msg["candle"]):
                    return
            await self.ws.send(json.dumps(msg))

    async def status(self, text: str) -> None:
        log.info(text)
        await self.send({"type": "status", "text": text, "ts": time.time()})

    async def _listen(self) -> None:
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = msg.get("type")
            if t == "replay_done":
                self.replay_done.set()
            elif t == "chart_more":
                asyncio.create_task(self._send_history(msg))
            elif t == "operator":
                await self._operator(msg)

    async def _operator(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "pause":
            self.paused = True
        elif cmd == "resume":
            self.paused = False
        elif cmd == "skip":
            self.skip_beat = True
        elif cmd == "skip_lesson":
            self.skip_lesson = True
        elif cmd == "market":
            self.force_market = True
        elif cmd == "mute":
            self.muted = not self.muted
            if self.muted and self.speaker:
                self.speaker.stop()
        elif cmd == "topic" and msg.get("text"):
            await self.topic_requests.put(msg["text"])
        elif cmd == "ask" and msg.get("text"):
            self.chat.offer(msg.get("user", "@operator"), msg["text"])
        elif cmd == "voice" and msg.get("voice"):
            await self._set_voice(msg.get("engine", "edge"), msg["voice"], bool(msg.get("preview")))
        elif cmd == "music_skip":
            if self.music is not None:
                self.music.skip()
        elif cmd == "alert_hit":
            # a price alert the host set on the chart just fired on the live candle: react to it on air, once
            label, price, direction = str(msg.get("label", "alert"))[:40], msg.get("price"), msg.get("direction", "")
            self.hot_alert = {"label": label, "price": price, "direction": direction, "at": time.time()}
            await self.status(f"alert fired: {label} at {price} ({direction})")
            return
        elif cmd == "tf" and msg.get("tf") in TF_SECONDS:
            self.pref_tf = msg["tf"]
            await self.show_live_chart(tf=msg["tf"])
            return
        elif cmd == "tiktok" and msg.get("username"):
            name = msg["username"].lstrip("@").strip()
            await self.chat.set_username(name)
            try:
                sp = Path("data_cache/settings.json")
                st = json.loads(sp.read_text()) if sp.exists() else {}
                st["tiktok"] = name
                sp.parent.mkdir(exist_ok=True)
                sp.write_text(json.dumps(st))
            except Exception:  # noqa: BLE001
                pass
            await self.status(f"chat: connecting to @{name}")
        await self.status(f"operator: {cmd} (paused={self.paused} muted={self.muted})")
        await self.send(self._state_msg())

    def _state_msg(self) -> dict:
        return {"type": "state", "paused": self.paused, "muted": self.muted,
                "now_playing": getattr(self.music, "now_playing", "") if self.music is not None else ""}

    @staticmethod
    def _save_setting(key: str, value) -> None:
        """Merge one key into data_cache/settings.json (voice, chat username, music mode survive restarts)."""
        try:
            sp = Path("data_cache/settings.json")
            st = json.loads(sp.read_text()) if sp.exists() else {}
            st[key] = value
            sp.parent.mkdir(exist_ok=True)
            sp.write_text(json.dumps(st))
        except Exception as exc:  # noqa: BLE001
            log.warning("settings: could not save %s: %s", key, exc)

    async def _set_voice(self, engine: str, voice: str, preview: bool) -> None:
        """Switch the voice live (operator console). Persisted to data_cache/settings.json."""
        if self.speaker is None:
            return
        target = self.speaker
        try:
            if engine == "chatterbox":
                prim = getattr(target, "primary", target)
                if getattr(prim, "engine", "") != "chatterbox":
                    await self.status("chatterbox engine is not the primary voice (set TTS_ENGINE=chatterbox and restart)")
                    return
                ref = Path("app/voice/ref") / (voice if voice.endswith(".wav") else f"{voice}.wav")
                if ref.exists():
                    prim.voice = str(ref)
                    prim._cache.clear()
                if hasattr(target, "primary_disabled_until"):
                    target.primary_disabled_until = 0.0
            elif engine == "kokoro":
                sec = getattr(target, "secondary", None)
                if sec is not None:
                    sec.voice = voice
                    target.primary_disabled_until = time.time() + 10 * 365 * 86400  # stay on the local voice
                else:
                    target.voice = voice
            else:
                prim = getattr(target, "primary", target)
                prim.voice = voice
                if hasattr(prim, "_cache"):
                    prim._cache.clear()
                if hasattr(target, "primary_disabled_until"):
                    target.primary_disabled_until = 0.0
            self._save_setting("engine", engine)
            self._save_setting("voice", voice)
            await self.status(f"voice set to {engine}:{voice}")
            if preview:
                await self.say(f"New voice check. This is how I sound now. Still Haddan, still no signals.")
        except Exception as exc:  # noqa: BLE001
            await self.status(f"voice change failed: {exc}")

    # ------------------------------------------------------------------ speaking
    def mood(self, value: str) -> None:
        if self.speaker is not None and hasattr(self.speaker, "mood"):
            self.speaker.mood = value

    def _bank(self, name: str) -> list[str]:
        return self._recent_lines.setdefault(name, [])

    def _music_lift(self, on: bool) -> None:
        if not self.music or not getattr(self.music, "enabled", False):
            return
        if self._music_base is None:
            self._music_base = self.music.level
        self.music.set_level(min(0.5, self._music_base * 1.6) if on else self._music_base)

    _NAME_FIRST = re.compile(r"^(@?[A-Za-z][A-Za-z0-9_.]{1,23}),\s+(?=[a-z])")

    async def murmur(self) -> None:
        """A quiet word to himself while drawing or waiting ("mm", "okay", "right, so"), at most every half minute."""
        if not self.speaker or self.muted or time.time() - self._last_murmur < 30:
            return
        self._last_murmur = time.time()
        try:
            from .voice import sfx
            clip = sfx.get("murmur", self.speaker.out_rate) if sfx.available() and hasattr(self.speaker, "play_audio") else None
            if clip is not None:
                async for ev in self.speaker.play_audio(clip, "murmur"):
                    if ev["event"] == "level":
                        await self.send({"type": "mouth", "level": ev["level"] * 0.5})
            else:
                self.speaker.plan_override = {"murmur": True}
                async for ev in self.speaker.speak(random.choice(MURMURS)):
                    if ev["event"] == "level":
                        await self.send({"type": "mouth", "level": ev["level"] * 0.5})
            await self.send({"type": "mouth", "level": 0})
        except Exception as exc:  # noqa: BLE001
            log.debug("murmur: %s", exc)

    async def say(self, text: str, mood: str | None = None, *, lesson: bool = False) -> None:
        text = " ".join(text.split())
        if not text:
            return
        # a name first, then a beat, then the answer: "Maria. Short answer..." (its own tiny sentence = its own gap)
        text = self._NAME_FIRST.sub(lambda m: f"{m.group(1)}. ", text, count=1)
        rep = deai_clean(text)
        if rep.fixes:
            log.info("deai: %d fix(es) %s | %s", rep.count, rep.fixes[:4], text[:90])
        text = rep.text
        if not text:
            return
        log.info("say: %s", text[:200])
        text = energize(text, mood or getattr(self.speaker, "mood", None))
        if getattr(self.speaker, "expressive", False):
            text = self.nonverbal.decorate(text, mood or getattr(self.speaker, "mood", None))
            if "[" in text:
                log.info("nonverbal: %s", text[:110])
        self._music_lift(mood in ("excited", "hype"))
        if mood:
            self.mood(mood)
            if mood in ("cheerful", "excited", "hype"):
                await self.send({"type": "react", "kind": "gesture"})
            elif mood == "considerate":
                await self.send({"type": "react", "kind": "considerate"})
        if self.music:
            self.music.duck(True)
        self.recent_says.append(text)
        self.recent_says = self.recent_says[-12:]
        cur_mood = getattr(self.speaker, "mood", "teach") if self.speaker else "teach"
        from .voice.tags import strip as _strip_tags
        from .voice.kokoro_tts import split_sentences as _split
        spoken = humanize_text(humanize(text), cur_mood)
        spoken = self.slips.apply(spoken, cur_mood)
        if not getattr(self.speaker, "expressive", False):
            spoken = _strip_tags(spoken)
        if self.speaker and not self.muted:
            sents = _split(spoken)
            idx = -1
            cut_at: int | None = None
            self._in_lesson_speech = lesson
            try:
                async for ev in self.speaker.speak(spoken):
                    if ev["event"] == "sentence":
                        idx += 1
                        await self.send({"type": "caption", "text": _strip_tags(ev["text"]), "duration_ms": ev["duration_ms"]})
                        # a real move on the live chart mid-lesson: break off like a person would, react, then come back
                        hot = self._interrupt_hot
                        if lesson and hot is not None and time.time() - hot.ts < 25 and idx >= 1 and len(sents) - idx >= 2 \
                                and time.time() - self._last_interrupt > 600:
                            cut_at = idx
                            self.speaker.stop()
                    elif ev["event"] == "level":
                        await self.send({"type": "mouth", "level": ev["level"]})
                    elif ev["event"] == "error":
                        await self.status(f"voice error: {ev['error']}")
            finally:
                self._in_lesson_speech = False
            await self.send({"type": "mouth", "level": 0})
            if cut_at is not None:
                await self._interrupt_for_move(sents[cut_at:])
                return
        else:
            dur = int(len(spoken.split()) / 2.6 * 1000)
            await self.send({"type": "caption", "text": _strip_tags(spoken), "duration_ms": dur})
            await asyncio.sleep(dur / 1000)
        if self.music:
            self.music.duck(False)
        self.last_speech_end = time.time()

    async def _interrupt_for_move(self, remaining: list[str]) -> None:
        """He stopped mid-sentence because the chart moved: react in the moment, then pick the thread back up."""
        hot, self._interrupt_hot = self._interrupt_hot, None
        self._last_interrupt = time.time()
        if hot is None:
            return
        q = getattr(self.quotes, "latest", {}).get(hot.symbol) if self.quotes is not None else None
        price = fmt_price(q["price"]) if q else fmt_price(hot.price)
        await self.send({"type": "react", "kind": "glance", "side": "center"})
        opener = random.choice(["Hold on, hold on.", "Wait, look at that.", "Oh, hang on.", "Okay, stop, look at this."])
        where = "up" if hot.direction == "up" else "down"
        await self.say(f"{opener} {spoken_symbol(hot.symbol)} just moved {abs(hot.pct):.2f} percent {where} in a minute, {price} now. "
                       f"That is a real move while we're talking. Watch where this candle closes before you read anything into it.", mood="excited")
        if self.memory is not None:
            self.memory.remember(f"Live move mid-lesson: {hot.symbol} {hot.pct:+.2f}% to {price}", kind="event")
        await asyncio.sleep(0.6)
        back = random.choice(["Okay. Where was I.", "Right, back to it.", "Okay, so, as I was saying.", "Anyway."])
        await self.say(back + " " + " ".join(remaining), mood="teach")

    def prefetch(self, text: str) -> None:
        if self.speaker and hasattr(self.speaker, "prefetch") and text:
            self.speaker.prefetch(humanize(text))

    async def _wait_if_paused(self) -> None:
        while self.paused:
            await asyncio.sleep(0.3)

    # ------------------------------------------------------------------ chart helpers
    CHART_HISTORY_BARS = 400   # bars loaded behind the analysis window so zooming out keeps real candles

    async def _with_history(self, raw_symbol: str, tf: str, candles: list[dict], bars: int | None = None) -> list[dict]:
        """Prepend older real bars (from the store / sources) in front of the analysis window for display."""
        if not candles:
            return candles
        step = TF_SECONDS.get(tf, 60)
        first = int(candles[0]["time"])
        try:
            older = await self.data.get_candles(raw_symbol, tf, first - step * (bars or self.CHART_HISTORY_BARS), first - 1)
        except Exception as exc:  # noqa: BLE001
            await self.status(f"history for {raw_symbol} {tf} failed: {exc}")
            return candles
        older = [dict(c) for c in older if int(c["time"]) < first]
        return older + candles

    async def _send_history(self, msg: dict) -> None:
        """The stage scrolled to its left edge: send the next page of older bars (or an end marker)."""
        tf = msg.get("tf") or getattr(self, "chart_tf", "15m")
        raw = getattr(self, "current_symbol_raw", None)
        if tf not in TF_SECONDS or not raw or msg.get("symbol") != self.current_symbol:
            return
        before = int(msg.get("before") or 0)
        step = TF_SECONDS[tf]
        try:
            older = await self.data.get_candles(raw, tf, before - step * self.CHART_HISTORY_BARS, before - 1)
        except Exception as exc:  # noqa: BLE001
            await self.status(f"history page failed: {exc}")
            older = []
        older = [dict(c) for c in older if int(c["time"]) < before]
        await self.send({"type": "chart", "action": "prepend", "symbol": self.current_symbol, "tf": tf, "candles": older, "end": len(older) < 5})

    async def perform(self, action: dict) -> bool:
        """Send one chart action to the stage; returns True if a replay was started."""
        d = dict(action)
        replay = False
        if d["action"] == "load":
            candles = await self.data.get_candles(d["symbol"], d["tf"], iso_to_unix(d["start"]), iso_to_unix(d["end"]))
            if not candles:
                await self.status(f"no candles for {d['symbol']} {d['tf']}; skipping load")
                return False
            step = TF_SECONDS[d["tf"]]
            candles = self._extend_with_live(pretty_symbol(d["symbol"]), d["tf"], candles)
            d["candles"] = await self._with_history(d["symbol"], d["tf"], candles)
            self._last_loaded = candles
            self.current_symbol_raw = d["symbol"]
            d["symbol"] = pretty_symbol(d["symbol"])
            self.current_symbol = d["symbol"]
            live = time.time() - candles[-1]["time"] < 2 * step + 120
            self.chart_is_live = live
            self.chart_tf = d["tf"]
            self._last_bar = dict(candles[-1])
            self.live_symbol = d["symbol"] if live else None
            self.replay_done.clear()
            replay = bool(d.get("replay"))
            if replay:
                d["pace_ms"] = min(int(d.get("pace_ms", 60)), 45)   # quick draw-in, the right edge is now
            d["note"] = f"live · {d['tf']}" if live else f"history · {datetime.fromtimestamp(candles[0]['time'], timezone.utc).strftime('%d %b %Y')} to {datetime.fromtimestamp(candles[-1]['time'], timezone.utc).strftime('%d %b %Y')}"
        convert_times(d)
        await self.send({"type": "chart", **d})
        return replay

    # ------------------------------------------------------------------ segments
    async def intro(self) -> None:
        self.mood(self.base_mood)
        await self.send({"type": "mode", "value": "live"})
        await self.send({"type": "lesson", "title": "Welcome to the chart room", "module": "live", "step": 0, "total": 0})
        chart = "gold" if primary_symbol() == "XAUUSD" else "Bitcoin"
        await self.say(self.picker.pick("greeting"))
        await self.say(f"It's {session_name()} right now, so {chart} is the chart of the hour. {next_change().capitalize()}.")
        if self.memory is not None:
            self.memory.remember(f"Stream session started during {session_name()}, chart of the hour {chart}", kind="event")

    async def social_moments(self) -> None:
        """Welcome joiners (batched), thank follows/gifts/shares, nudge likes; all rate-limited."""
        now = time.time()
        gifts, follows, shares, likes = [], [], [], 0
        while not self.chat.events.empty():
            kind, user, extra = self.chat.events.get_nowait()
            name = speakable_name(user, fallback="")
            if kind == "join":
                if name and name not in self.pending_joins:
                    self.pending_joins.append(name)
            elif kind == "follow":
                follows.append(name or "a new follower")
            elif kind == "gift":
                gifts.append((name or "someone", extra.get("gift", "a gift"), extra.get("count", 1)))
            elif kind == "share":
                shares.append(name or "someone")
            elif kind == "like":
                likes += int(extra.get("count", 1))
        self.likes_total += likes
        for user, gift, count in gifts[:2]:
            await self.send({"type": "react", "kind": "celebrate"})
            await self.say(showman.pick(showman.GIFT_HYPE, self._bank("gift"), name=user, gift=(f"{count} x {gift}" if count > 1 else gift)), mood="excited")
            self.last_thanks = now
            if self.memory is not None:
                self.memory.remember(f"Viewer {user} sent a gift: {count} x {gift}", kind="event", viewer=user)
        if follows and now - self.last_thanks > 20:
            if len(follows) == 1:
                await self.say(self.picker.pick("thanks_follow", name=follows[0]), mood="warm")
            else:
                await self.say(f"New follows from {', '.join(follows[:3])}. Thank you all, welcome to the chart room.", mood="warm")
            self.last_thanks = time.time()
            if self.memory is not None:
                for u in follows:
                    self.memory.remember(f"Viewer {u} followed the stream", kind="event", viewer=u)
        if shares and now - self.last_thanks > 20:
            await self.say(showman.pick(showman.SHARE_HYPE, self._bank("share"), name=shares[0]), mood="cheerful")
            self.last_thanks = time.time()
        if self.pending_joins and now - self.last_welcome > WELCOME_EVERY_S:
            names = self.pending_joins[:3]
            extra = f" and {len(self.pending_joins) - 3} more" if len(self.pending_joins) > 3 else ""
            topic = (self.current_title or "reading the chart").lower()
            if ENERGY >= 0.7:
                await self.say(showman.pick(showman.WELCOME_FAST, self._bank("welcome"), names=", ".join(names) + extra, topic=topic), mood="cheerful")
            else:
                await self.say(self.picker.pick("welcome", names=", ".join(names) + extra, topic=topic), mood="warm")
            self.pending_joins = []
            self.last_welcome = time.time()
        # like goal: real counts only, announced on crossing the goal or every ~3 minutes while climbing
        if self.likes_total:
            await self.send({"type": "goal", "likes": self.likes_total, "target": self.like_target, "viewers": self.chat.viewers})
        if self.likes_total >= self.like_target:
            hit, self.like_target = self.like_target, next_like_target(self.likes_total)
            await self.send({"type": "react", "kind": "celebrate"})
            await self.say(showman.pick(showman.LIKE_HIT, self._bank("likehit"), target=f"{hit:,}", next_target=f"{self.like_target:,}"), mood="excited")
            self.last_like_call = time.time()
        elif likes and now - self.last_like_call > 180 and self.likes_total >= 20:
            await self.say(showman.pick(showman.LIKE_GOAL, self._bank("likegoal"), likes=f"{self.likes_total:,}", target=f"{self.like_target:,}"), mood="cheerful")
            self.last_like_call = time.time()
        # viewer milestones (every +25 viewers, from the live room count)
        v = int(self.chat.viewers or 0)
        if v >= 10 and v - self.viewers_announced >= 25:
            self.viewers_announced = v
            await self.say(showman.pick(showman.VIEWERS_MILESTONE, self._bank("viewers"), viewers=v, topic=(self.current_title or "reading the chart").lower()), mood="cheerful")

    async def retention_beats(self) -> None:
        """Re-orient newcomers every ~2.5 minutes and give the chat something easy to do every ~4 minutes."""
        now = time.time()
        if now - self.last_hook > HOOK_EVERY_S and self.current_title:
            await self.say(self.picker.pick("hook", topic=self.current_title.lower()), mood="hype")
            if self.community.due_in_hook(now):
                await self.say(self.community.line(), mood="warm")
            self.last_hook = time.time()
        elif now - self.last_prompt > 240:
            answers = await self.ask_audience(self.picker.pick("chat_prompt"), wait_s=20.0 if self.chat.connected else 3.0, mood="warm")
            self.last_prompt = time.time()
            cb = self._callback_line(answers)
            if cb:
                await self.say(cb + " " + random.choice(["I read every one of those.", "Love that.", "Good, keep them coming."]), mood="warm")
            await self.send({"type": "question", "clear": True})

    async def answer_questions(self, max_n: int = 1, max_rank: int = 2) -> None:
        """max_rank 0 = only urgent questions, 1 = urgent + medium, 2 = everything incl. idle chatter."""
        for _ in range(max_n):
            r = self.chat.pop(max_rank)
            if r is None:
                return
            q = r.q
            now = time.time()
            self.answered_texts = [(ts, t) for ts, t in self.answered_texts if now - ts < 600]
            if is_injection(q.text):
                await self.status(f"ignored instruction-like comment from @{q.user}")
                continue
            if is_duplicate(q.text, [t for _, t in self.answered_texts]):
                await self.status(f"skipping duplicate question from @{q.user}: {q.text[:60]}")
                continue
            if now - q.ts > STALE_REPLY_S.get(min(r.rank, 2), 90.0):
                await self.status(f"dropping stale comment from @{q.user} ({int(now - q.ts)} s old)")
                continue
            self.chat.answered += 1
            await self.status(f"answering @{q.user} (priority {['high', 'medium', 'low'][min(r.rank, 2)]}): {q.text[:80]}")
            await self.send({"type": "mode", "value": "q&a"})
            await self.send({"type": "question", "user": f"@{q.user}", "text": q.text})
            self.mood("calm")
            spoken_name = speakable_name(q.user)
            mood = None
            if self.responder and brain_available():
                reply = await self.responder.reply(spoken_name, q.text, self.current_title, self.recent_says, self.current_symbol, handle=q.user)
                text = reply.say
                mood = DELIVERY_TO_MOOD.get(reply.delivery)
                if reply.follow_up and reply.answered:
                    self.promises.append({"text": reply.follow_up, "made_at": time.time(), "user": spoken_name})
                    await self.status(f"promise noted: {reply.follow_up[:80]}")
            else:
                dec = self._offline_decision(q.user, q.text)
                text = dec.speech
                mood = DELIVERY_TO_MOOD.get(dec.delivery)
                if text and self.memory is not None:
                    self.memory.remember(f"Viewer {q.user} asked: {q.text[:200]} | Haddan answered: {text[:200]}", kind="qa", viewer=q.user)
            if not text:
                await self.status(f"chose silence for @{q.user}: {q.text[:60]}")
                await self.send({"type": "question", "clear": True})
                await self.send({"type": "mode", "value": "lesson"})
                continue
            self.answered_texts.append((time.time(), q.text))
            if mood == "cheerful":
                await self.send({"type": "react", "kind": "celebrate"})
            await self.say(text, mood=mood)
            self.questions_answered += 1
            if mood in ("cheerful", "teach", "curious") and self.current_title and random.random() < 0.5:
                await self.say(self.picker.pick("bridge_exchange", topic=self.current_title.lower()), mood="cheerful")
            await asyncio.sleep(0.8)
            await self.send({"type": "question", "clear": True})
            await self.send({"type": "mode", "value": "lesson"})

    def _offline_decision(self, handle: str, question: str):
        """LLM-free reply through the host policy; recognises regulars from memory."""
        facts = []
        if self.quotes is not None and self.current_symbol:
            q = getattr(self.quotes, "latest", {}).get(self.current_symbol)
            facts.append(f"{self.current_symbol} {q['price']} ({int(time.time() - q['ts'])} s old)" if q else "No current price is available.")
        memory = []
        if self.memory is not None:
            try:
                memory = [str(n) for n in self.memory.viewer_notes(handle, limit=2)]
            except Exception:  # noqa: BLE001
                memory = []
        state = HostState(event="chat", topic=self.current_title or "reading the live chart", facts=facts,
                          chat=[Comment("c1", handle, question)], recent_host_text=self.recent_says[-6:], memory=memory,
                          speech_busy=False, question_pending=self.pending_question is not None,
                          answered_recently=[t for _, t in self.answered_texts])
        dec = reply_for(state.chat[0], state)
        if memory and dec.speech and dec.action == "respond":
            dec.speech = random.choice(["Welcome back, ", "Good to see you again, ", "Hey again, "]) + dec.speech[0].lower() + dec.speech[1:]
        return dec

    def _canned_reply(self, user: str, question: str) -> str:
        """Offline replies: recognise regulars from memory, deflect predictions, teach the method."""
        back = ""
        if self.memory is not None:
            try:
                if self.memory.viewer_notes(user, limit=1):
                    back = random.choice(["Welcome back, ", "Good to see you again, ", "Hey again, "])
            except Exception:  # noqa: BLE001
                back = ""
        name = f"{back}{user}" if back else random.choice(["Good one, ", "Okay ", "Thanks ", "Hey "]) + user
        q = question.lower()
        if any(w in q for w in ("going to", "will it", "pump", "dump", "100k", "target", "should i buy", "should i sell", "signal")):
            return f"{name}. I don't predict and I don't signal, that's the deal here. What I can tell you is where the idea would be wrong: find the level behind the move, and if price trades through it, the story is over."
        if any(w in q for w in ("real", "human", "bot", "ai")):
            return f"{name}. Fair question. I'm Haddan, the voice you're hearing in the chart room right now. The charts are real, the analysis is real, nothing here is advice. Ask me anything about the chart."
        return random.choice([
            f"{name}. Short answer: look at where it happens on the chart first, then ask what would prove the idea wrong. That's the whole method.",
            f"{name}. Good question. The location matters more than the pattern. A setup at a level is a setup; the same shape in the middle of nowhere is noise.",
            f"{name}. Here's how I'd think about it: find the last swing, find the level, and decide where you'd be wrong before you decide anything else.",
        ])

    async def ask_audience(self, question: str, wait_s: float = 25.0, mood: str = "warm") -> list[tuple[str, str]]:
        """Ask ONE answerable question, then actually give the chat time; returns (user, answer) pairs."""
        await self.send({"type": "question", "user": "Chat", "text": question})
        self.pending_question = {"text": question, "asked_at": time.time()}
        self.chat.answer_sink = []
        await self.say(question, mood=mood)
        await self.send({"type": "react", "kind": "attentive"})
        self._music_lift(True)
        t0 = time.time()
        hinted = False
        filled = False
        try:
            while time.time() - t0 < wait_s:
                await asyncio.sleep(1.0)
                if self.skip_beat or self.skip_lesson or self.force_market:
                    break
                if len(self.chat.answer_sink) >= 3 and time.time() - t0 > 8:
                    break
                # a person does not stand in silence while the room thinks: one easy line at five seconds, the hint later
                if not filled and wait_s >= 15 and time.time() - t0 >= 5 and not self.chat.answer_sink:
                    filled = True
                    await self.say(self.picker.pick("wait_filler"), mood="warm")
                if not hinted and wait_s >= 15 and time.time() - t0 >= 12 and not self.chat.answer_sink:
                    hinted = True
                    await self.say(self.picker.pick("hint", hint=hint_for(question)), mood="curious")
        finally:
            answers, self.chat.answer_sink = list(self.chat.answer_sink or []), None
            self.pending_question = None
            self._music_lift(False)
        return answers

    def _first_correct(self, answers: list[tuple[str, str]], answer_text: str) -> tuple[str, str] | None:
        """(speakable name, their answer) for the first viewer whose answer appears in the real answer; never guessed."""
        import re as _re
        low = answer_text.lower()
        for user, text in answers:
            tok = text.strip().strip("!.?,").lower()
            if not tok or len(tok) > 30:
                continue
            if _re.search(r"\b" + _re.escape(tok) + r"\b", low):
                name = speakable_name(user, fallback="")
                if name:
                    return name, text.strip().strip("!.?,")
        return None

    def _callback_line(self, answers: list[tuple[str, str]]) -> str:
        """Refer back to real answers by name (never invent participation)."""
        if not answers:
            return ""
        seen, parts = set(), []
        for user, text in answers:
            name = speakable_name(user, fallback="")
            if not name or name in seen:
                continue
            seen.add(name)
            parts.append(f"{name} says {text}")
            if len(parts) == 3:
                break
        if not parts:
            return random.choice(["A few answers in, nice.", "Answers coming in, good."])
        more = f", and {len(answers) - len(parts)} more" if len(answers) > len(parts) else ""
        return ", ".join(parts) + more + "."

    def _tease_next(self) -> str:
        """What is actually coming next (never a promise we cannot keep): the queued lesson, else the live chart."""
        try:
            nxt = self.lesson_queue._queue[0]  # noqa: SLF001
            return f"{nxt.topic.lower()}, on the live chart"
        except (IndexError, AttributeError):
            return "the live chart, and I'll mark where the idea would be wrong"

    async def hot_moments(self) -> None:
        """React out loud to a real move that happened while Haddan was busy (fresh ones only)."""
        now = time.time()
        alert = getattr(self, "hot_alert", None)
        if alert and now - alert["at"] < HOT_EVENT_TTL_S:
            # an alert line on the chart just got crossed: say exactly what it was and what it does not mean
            self.hot_alert = None
            await self.send({"type": "react", "kind": "glance", "side": "center"})
            where = "up through" if alert["direction"] == "up" else "down through"
            await self.say(f"Hold on, the alert just fired. Price went {where} the {alert['label']} line at {fmt_price(alert['price'])}. "
                           f"That is a line being touched, not a decision. Watch where this candle closes.", mood="excited")
        elif alert:
            self.hot_alert = None
        fresh = [h for h in self.hot_events if now - h.ts < HOT_EVENT_TTL_S]
        self.hot_events = []
        if not fresh:
            return
        h = fresh[-1]
        q = getattr(self.quotes, "latest", {}).get(h.symbol) if self.quotes is not None else None
        price = fmt_price(q["price"]) if q else fmt_price(h.price)
        await self.send({"type": "react", "kind": "glance", "side": "center"})
        await self.say(showman.pick(showman.REACTIONS, self._bank("react"), sym=spoken_symbol(h.symbol), pct=f"{abs(h.pct):.2f}", dir=h.direction, price=price), mood="excited")
        if self.memory is not None:
            self.memory.remember(f"Live move: {h.symbol} {h.pct:+.2f}% in a minute to {price} during {self.current_title or 'live chart'}", kind="event")

    async def quiet_initiative(self) -> None:
        """Chat is quiet and nothing is queued: Haddan starts something. Rotates observation, mini challenge,
        continuation, and the occasional disclaimer; the observation is grounded in the live quote only."""
        if time.time() - self.last_speech_end < QUIET_INITIATIVE_S[0]:
            await asyncio.sleep(max(0.0, QUIET_INITIATIVE_S[0] - (time.time() - self.last_speech_end)))
        self._initiatives += 1
        k = self._initiatives % 4
        q = getattr(self.quotes, "latest", {}).get(self.current_symbol or "") if self.quotes is not None else None
        if k == 0 and q:
            await self.send({"type": "react", "kind": "glance", "side": "center"})
            price = f"{q['price']:,.1f}" if q["price"] >= 1000 else f"{q['price']:.2f}" if q["price"] >= 10 else f"{q['price']:.4f}"
            chg = f"{'up' if q['chg'] >= 0 else 'down'} {abs(q['chg']):.2f} percent"
            await self.say(self.picker.pick("quiet_observation", symbol=self.current_symbol, price=price, chg=chg), mood="teach")
        elif k == 1:
            answers = await self.ask_audience(self.picker.pick("mini_challenge", topic=(self.current_title or "the live chart").lower()), wait_s=20.0 if self.chat.connected else 3.0, mood="curious")
            cb = self._callback_line(answers)
            await self.say((cb + " Good, that's the kind of noticing that makes a trader.") if cb else self.picker.pick("no_answers"), mood="cheerful" if cb else "warm")
            await self.send({"type": "question", "clear": True})
        elif k == 2:
            await self.say(self.picker.pick("no_question_filler"), mood="cheerful")
        else:
            await self.say(self.picker.pick("disclaimer"), mood="serious")

    async def deliver_promises(self, max_n: int = 1) -> None:
        """Finish what Haddan promised (continuity); stale promises are dropped quietly, never claimed."""
        now = time.time()
        self.promises = [p for p in self.promises if now - p["made_at"] < 30 * 60 and not p.get("done")]
        if not self.promises or self.responder is None or not brain_available():
            return
        for p in self.promises[:max_n]:
            text = await self.responder.deliver(p["text"], self.current_title, self.recent_says, self.current_symbol)
            p["done"] = True
            if text:
                await self.status(f"delivering promise: {p['text'][:80]}")
                await self.say(text, mood="teach")
                if self.memory is not None:
                    self.memory.remember(f"Haddan delivered a promise to {p.get('user', 'chat')}: {p['text'][:160]} -> {text[:200]}", kind="promise")
        self.promises = [p for p in self.promises if not p.get("done")]

    async def play_lesson(self, script: LessonScript) -> None:
        started = time.time()
        try:
            await self._play_lesson(script)
        finally:
            self._segment("lesson", script.topic, started, time.time())
            if self.memory is not None and script.beats:
                self.memory.remember(
                    f"Taught lesson '{script.topic}' on {self.current_symbol or 'chart'} during {session_name()}. "
                    f"Opened with: {script.beats[0].say[:120]} Recap: {script.beats[-1].say[:160]}",
                    kind="lesson", meta={"topic": script.topic, "module": script.module},
                )

    async def _play_lesson(self, script: LessonScript) -> None:
        self.current_title = script.topic
        self.skip_lesson = False
        self._deep_done = False
        self._lesson_candles = None
        header = {"type": "lesson", "title": script.topic, "module": script.module, "summary": script.summary, "total": len(script.beats)}
        await self.send({"type": "mode", "value": "lesson"})
        await self.send({**header, "step": 0})
        for i, beat in enumerate(script.beats, 1):
            await self._wait_if_paused()
            if self.skip_lesson:
                break
            self.skip_beat = False
            await self.send({**header, "step": i})
            await self.send({"type": "beat"})
            wait_replay = False
            for act in beat.chart:
                try:
                    wait_replay = await self.perform(act.model_dump()) or wait_replay
                except Exception as exc:  # noqa: BLE001
                    await self.status(f"chart action failed: {exc}")
            nxt = script.beats[i].say if i < len(script.beats) else (script.quiz.question if script.quiz else "")
            self.prefetch(nxt)
            if i + 1 < len(script.beats):
                self.prefetch(script.beats[i + 1].say)         # two beats ahead: the voice is never waiting on the GPU
            if beat.ask:
                self.prefetch(beat.ask)
            await self.say(beat.say, lesson=True)
            if beat.ask and not self.skip_lesson:
                answers = await self.ask_audience(beat.ask, wait_s=20.0 if self.chat.connected else 4.0, mood="curious")
                winner = self._first_correct(answers, (script.quiz.answer if script.quiz else "") + " " + beat.ask)
                if winner:
                    await self.send({"type": "react", "kind": "celebrate"})
                    await self.say(self.picker.pick("celebrate", name=winner[0], detail=winner[1] + "."), mood="cheerful")
                elif answers:
                    await self.say(self._callback_line(answers), mood="cheerful")
                await self.send({"type": "question", "clear": True})
            if wait_replay:
                try:
                    await asyncio.wait_for(self.replay_done.wait(), timeout=40)
                except asyncio.TimeoutError:
                    pass
                self._lesson_candles = self._last_loaded
            if (beat.deep or (i == max(2, len(script.beats) - 2) and not getattr(self, "_deep_done", False))) and getattr(self, "_lesson_candles", None):
                self._deep_done = True
                await self.deep_markup(self._lesson_candles, narrate=True, max_narrated=6)
            await asyncio.sleep(beat.pause_ms / 1000)
            await self.hot_moments()
            await self.answer_questions(1, max_rank=0)
            if i == len(script.beats) - 2 and ENERGY >= 0.7:
                tease = self._tease_next()
                if tease:
                    await self.say(showman.pick(showman.CLIFFHANGER, self._bank("cliff"), tease=tease), mood="show")
            if i % 3 == 0:
                await self.answer_questions(1, max_rank=1)
                await self.social_moments()
                await self.retention_beats()
                self.mood(self.base_mood)
        if script.quiz and not self.skip_lesson:
            self.prefetch(script.quiz.answer)
            answers = await self.ask_audience(script.quiz.question, wait_s=20.0 if self.chat.connected else 4.0, mood="curious")
            winner = self._first_correct(answers, script.quiz.answer)
            if winner:
                await self.send({"type": "react", "kind": "celebrate"})
                await self.say(self.picker.pick("celebrate", name=winner[0], detail=winner[1] + "."), mood="excited")
            elif answers:
                await self.say(self._callback_line(answers), mood="cheerful")
            else:
                await self.say(self.picker.pick("no_answers"), mood="warm")
            await self.say(script.quiz.answer, mood="teach")
            await self.send({"type": "question", "clear": True})
            await self.deliver_promises()
        self.lessons_played += 1

    async def show_live_chart(self, symbol: str | None = None, tf: str = "1m") -> list[dict]:
        """Load the live chart of the chart of the hour from tick-built 1m candles (or recent history as fallback)."""
        symbol = symbol or primary_symbol()
        name = pretty_symbol(symbol)
        candles: list[dict] = []
        if tf == "1m" and getattr(self, "pref_tf", None):
            tf = self.pref_tf            # the operator picked a timeframe on the chart toolbar
        if tf == "1m" and self.quotes is not None and len(self.quotes.candles.get(name, [])) >= 30:
            candles = list(self.quotes.candles[name])[-180:]
        else:
            if tf == "1m":
                tf = "15m"
            try:
                candles = [dict(c) for c in await self.data.recent(symbol, tf, 90)]
                candles = self._extend_with_live(name, tf, candles)
            except Exception as exc:  # noqa: BLE001
                await self.status(f"live chart data failed: {exc}")
        if not candles:
            return []
        self.current_symbol_raw = symbol
        shown = await self._with_history(symbol, tf, candles)
        await self.send({"type": "chart", "action": "load", "symbol": name, "tf": tf, "candles": shown, "replay": False, "note": f"live · {tf}"})
        self.current_symbol = name
        self.live_symbol = name
        self.chart_is_live = True
        self.chart_tf = tf
        self._last_bar = dict(candles[-1])
        self._last_loaded = list(candles)
        return candles

    async def market_tour(self) -> None:
        """Descriptive, no-prediction look at the chart of the hour, candles updating live."""
        symbol = primary_symbol()
        tf = "15m"
        name = pretty_symbol(symbol)
        market = "gold" if symbol == "XAUUSD" else "Bitcoin"
        await self.say(self.picker.pick("countdown"), mood="hype")
        await asyncio.sleep(6)
        await self.send({"type": "mode", "value": "market"})
        await self.send({"type": "lesson", "title": f"Live chart: {name}", "module": "market tour", "step": 0, "total": 0})
        candles = await self.show_live_chart(symbol)
        tf = "1m" if self.quotes is not None and len(self.quotes.candles.get(name, [])) >= 30 else "15m"
        if len(candles) < 20:
            return
        self.current_title = f"Live chart: {name}"
        day = [c for c in candles if c["time"] >= int(time.time()) - 86400] or candles
        hi, lo, last = max(c["high"] for c in day), min(c["low"] for c in day), day[-1]["close"]
        pos = (last - lo) / max(1e-9, hi - lo)
        where = "near the top of" if pos > 0.75 else "near the bottom of" if pos < 0.25 else "in the middle of"
        chg = (last / day[0]["open"] - 1) * 100
        rng_pct = (hi - lo) / lo * 100
        self._last_loaded = candles
        self.mood("hype" if abs(chg) >= 1.2 else "teach")
        lines = [
            self.picker.pick("market_intro", market=market, tf="one minute" if tf == "1m" else "fifteen minute"),
            self.picker.pick("market_describe", price=_spoken(last), direction="up" if chg >= 0 else "down", chg=f"{abs(chg):.1f}",
                             lo=_spoken(lo), hi=_spoken(hi), where=where),
        ]
        if rng_pct < 0.6:
            lines.append(self.picker.pick("boring"))
        lines.append(self.picker.pick("market_lesson"))
        if self.memory is not None and abs(chg) >= 2.0:
            self.memory.remember(f"{market} moved {chg:+.1f} percent over the day during {session_name()}; day range {_spoken(lo)} to {_spoken(hi)}", kind="event")
        try:   # live candle updates arrive through quotes_loop while chart_is_live
            for k, line in enumerate(lines):
                await self._wait_if_paused()
                if k + 1 < len(lines):
                    self.prefetch(lines[k + 1])
                await self.say(line)
                await asyncio.sleep(1.2)
            await self.deep_markup(candles, narrate=True, max_narrated=8)
            await self.answer_questions(2)
            await asyncio.sleep(4)
        finally:
            pass
        self.last_market_tour = time.time()
        self.force_market = False

    async def deep_markup(self, candles: list[dict], narrate: bool = True, max_narrated: int = 9, pace: float = 1.1) -> None:
        """The draft book: draw the full analysis on the chart step by step, narrating the key ones."""
        try:
            steps = await asyncio.to_thread(analyze, candles, self.current_symbol or "")
        except Exception as exc:  # noqa: BLE001
            await self.status(f"analysis failed: {exc}")
            return
        if not steps:
            return
        await self.status(f"deep markup: {len(steps)} drawings")
        self.mood("teach")
        narrated = 0
        nxt_say = [s.get("say") for s in steps if s.get("say")]
        cur_layer, cur_ids = None, []
        for st in steps:
            await self._wait_if_paused()
            if self.skip_lesson:
                break
            layer, keep = st.pop("layer", None), st.pop("keep", True)
            if layer != cur_layer:
                if cur_ids:        # the previous passing illustration leaves before the next one is drawn
                    for rid in cur_ids:
                        await self.send({"type": "chart", "action": "remove", "id": rid})
                    cur_ids = []
                cur_layer = layer
            if not keep and st.get("id"):
                cur_ids.append(st["id"])
            say = st.pop("say", None)
            if say and say in nxt_say:
                k = nxt_say.index(say)
                if k + 1 < len(nxt_say):
                    self.prefetch(nxt_say[k + 1])          # the next narrated line's voice starts synthesising now
            d = convert_times(dict(st))
            await self.send({"type": "chart", **d})
            await self.react("type")
            if say and narrate and narrated < max_narrated:
                narrated += 1
                await self.say(say, lesson=True)
                if self.memory is not None and narrated <= 3:
                    self.memory.remember(f"On {self.current_symbol or 'the chart'} Haddan said: {say[:220]}", kind="said", meta={"symbol": self.current_symbol or ""})
            else:
                if random.random() < 0.22:
                    await self.murmur()          # thinking out loud while the pen moves
                await asyncio.sleep(pace)

    async def _auto_markup(self, candles: list[dict]) -> None:
        """Mark the chart up the way a trader would: key levels, last swings, a trendline."""
        from .data import patterns

        try:
            lv = patterns.levels(candles, lookback=3, tolerance=0.0025)
            for h in sorted(lv, key=lambda x: -x.extra["touches"])[:2]:
                await self.send({"type": "chart", "action": "hline", "price": h.extra["price"], "label": h.label[:18],
                                 "color": "#4fd1c5" if h.label.startswith("support") else "#f5c542", "style": "dashed"})
                await asyncio.sleep(0.6)
            highs, lows = patterns.swing_points(candles, lookback=4)
            for hit, pos, shape in ((highs[-1] if highs else None, "aboveBar", "arrowDown"), (lows[-1] if lows else None, "belowBar", "arrowUp")):
                if hit:
                    await self.send({"type": "chart", "action": "marker", "time": hit.time, "text": hit.label, "position": pos, "shape": shape,
                                     "color": "#f56565" if pos == "aboveBar" else "#22c55e"})
            pts = lows[-2:] if len(lows) >= 2 and lows[-1].extra["price"] > lows[-2].extra["price"] else highs[-2:] if len(highs) >= 2 else []
            if len(pts) == 2:
                await asyncio.sleep(0.6)
                await self.send({"type": "chart", "action": "trendline", "t1": pts[0].time, "p1": pts[0].extra["price"], "t2": pts[1].time,
                                 "p2": pts[1].extra["price"], "label": "trend", "color": "#f56565", "extend": True})
            await self.react("type")
        except Exception as exc:  # noqa: BLE001
            log.debug("auto markup: %s", exc)

    async def ritual(self) -> None:
        """Small human moments between lessons."""
        kind = random.choice(["mistake", "mistake", "disclaimer", "ai_honest"])
        await self.send({"type": "mode", "value": "live"})
        await self.say(self.picker.pick(kind))
        self.last_ritual = time.time()

    # ------------------------------------------------------------------ lesson supply
    async def pregen_loop(self) -> None:
        while True:
            try:
                if not self.topic_requests.empty():
                    text = await self.topic_requests.get()
                    script = await (self.planner.plan_topic(text) if self.planner and not self.offline else self.template.plan_topic(self.curriculum, text))
                    await self.lesson_queue.put(script)
                    continue
                lesson = self.next_lesson()
                self._last_module = lesson.module
                if self.planner and not self.offline and brain_available():
                    try:
                        script = await self.planner.plan(lesson)
                    except Exception as exc:  # noqa: BLE001
                        await self.status(f"planner failed for {lesson.key} ({str(exc)[:120]}); using template")
                        script = await self.template.plan(lesson)
                else:
                    script = await self.template.plan(lesson)
                self.history[lesson.key] = time.time()
                self._save_history()
                await self.lesson_queue.put(script)   # blocks while 2 are ready
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("pregen error")
                await self.status(f"lesson generation error: {exc}")
                await asyncio.sleep(10)

    async def quotes_loop(self) -> None:
        """Forward real-time quotes/candles to the room screens (rate-limited per symbol)."""
        if self.quotes is None:
            return
        q = self.quotes.subscribe()
        last_sent: dict[str, float] = {}
        # seed the mini charts with whatever history the service already holds
        for sym, arr in self.quotes.candles.items():
            await self.send({"type": "kline", "symbol": sym, "candles": arr[-120:]})
        for sym, qt in self.quotes.latest.items():
            await self.send(qt)
        last_ticker = 0.0
        while True:
            msg = await q.get()
            key = f"{msg['type']}:{msg['symbol']}"
            now = time.time()
            if msg["type"] == "kline" and msg["symbol"] == self.live_symbol and "candle" in msg and self.chart_is_live:
                bar = self._aggregate_tick(msg["candle"])
                if bar:
                    await self.send({"type": "chart", "action": "update", "candle": bar})
            if now - last_sent.get(key, 0) < 0.4:
                continue
            last_sent[key] = now
            await self.send(msg)
            if msg["type"] == "quote":
                hot = self.moves.feed(msg["symbol"], float(msg["price"]), now)
                if hot and (hot.symbol == self.current_symbol or abs(hot.pct) >= 2 * showman.MOVE_THRESHOLDS.get(hot.symbol, 0.3)):
                    self.hot_events = [h for h in self.hot_events if now - h.ts < HOT_EVENT_TTL_S][-1:] + [hot]
                    if self._in_lesson_speech and hot.symbol == self.current_symbol and abs(hot.pct) >= 1.5 * showman.MOVE_THRESHOLDS.get(hot.symbol, 0.3):
                        self._interrupt_hot = hot      # big enough to break off a sentence for
                    await self.send({"type": "hot", "symbol": hot.symbol, "pct": hot.pct, "price": hot.price})
                    await self.send({"type": "react", "kind": "hype"})
            if msg["type"] == "quote" and now - last_ticker > 1.0:
                last_ticker = now
                items = []
                for sym in ("XAU/USD", "BTC/USD", "ETH/USD", "SOL/USD", "EUR/USD", "GBP/USD"):
                    qt = self.quotes.latest.get(sym)
                    if qt:
                        items.append({"symbol": sym.split("/")[0] if sym.endswith("/USD") and sym != "EUR/USD" and sym != "GBP/USD" else sym,
                                      "price": _fmt_price(qt["price"]), "chg": qt["chg"], "delayed": qt.get("delayed", False)})
                if items:
                    await self.send({"type": "ticker", "items": items})
                if self.current_symbol and self.quotes.latest.get(self.current_symbol):
                    qt = self.quotes.latest[self.current_symbol]
                    await self.send({"type": "live", "symbol": self.current_symbol, "price": qt["price"], "chg": qt["chg"], "live": self.chart_is_live})

    def _extend_with_live(self, name: str, tf: str, candles: list[dict]) -> list[dict]:
        """Append/refresh the most recent bars from the live 1-minute feed (tick-built), so the chart's
        right edge is the bar in progress even when the history source lags."""
        if self.quotes is None or not candles:
            return candles
        ticks = self.quotes.candles.get(name) or []
        if not ticks:
            return candles
        step = TF_SECONDS.get(tf, 60)
        out = list(candles)
        last_t = out[-1]["time"]
        bars: dict[int, dict] = {}
        for c in ticks:
            b = c["time"] - c["time"] % step
            if b < last_t:
                continue
            if b in bars:
                o = bars[b]; o["high"] = max(o["high"], c["high"]); o["low"] = min(o["low"], c["low"]); o["close"] = c["close"]
            else:
                bars[b] = {"time": b, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "volume": c.get("volume", 0.0)}
        for b in sorted(bars):
            if b == last_t:
                o = out[-1]; o["high"] = max(o["high"], bars[b]["high"]); o["low"] = min(o["low"], bars[b]["low"]); o["close"] = bars[b]["close"]
            else:
                out.append(bars[b])
        return out

    def _aggregate_tick(self, c1m: dict) -> dict | None:
        """Fold a live 1-minute candle into the current bar of the chart's timeframe."""
        tf = getattr(self, "chart_tf", "1m")
        step = TF_SECONDS.get(tf, 60)
        bucket = c1m["time"] - c1m["time"] % step
        last = getattr(self, "_last_bar", None)
        if last and last["time"] == bucket:
            last["high"] = max(last["high"], c1m["high"]); last["low"] = min(last["low"], c1m["low"]); last["close"] = c1m["close"]
        elif last and bucket < last["time"]:
            return None
        else:
            last = {"time": bucket, "open": c1m["open"], "high": c1m["high"], "low": c1m["low"], "close": c1m["close"], "volume": c1m.get("volume", 0.0)}
            self._last_bar = last
            if self._last_loaded is not None:
                self._last_loaded.append(dict(last))
        if self._last_loaded:
            self._last_loaded[-1] = dict(last)
        return dict(last)

    async def react(self, kind: str, side: str | None = None) -> None:
        await self.send({"type": "react", "kind": kind, "side": side})

    async def triage_loop(self) -> None:
        """Every few seconds: classify pending comments (spam / low / medium / high), queue them,
        and turn 'teach me X' requests into lesson topics. Also reports chat connection changes."""
        while True:
            try:
                if self.chat.connected != self._chat_was_connected:
                    self._chat_was_connected = self.chat.connected
                    await self.status(f"chat {'connected' if self.chat.connected else 'not connected'} (@{self.chat.unique_id or '-'}) {self.chat.last_error}")
                batch = self.chat.take_pending(15)
                if batch:
                    items = await self.triager.classify([(q.user, q.text) for q in batch])
                    for q, it in zip(batch, items):
                        if it.priority == "spam":
                            log.info("spam ignored: @%s %s", q.user, q.text[:60])
                            continue
                        self.chat.push(q, it.priority, it.topic)
                        if it.topic and time.time() - self.last_topic_from_chat > 600:
                            lesson = self.curriculum.find(it.topic)
                            if lesson:
                                self.last_topic_from_chat = time.time()
                                await self.topic_requests.put(it.topic)
                                await self.status(f"topic from chat (@{q.user}): {it.topic} -> {lesson.title}")
                                if self.memory is not None:
                                    self.memory.remember(f"Viewer {q.user} asked to learn about {it.topic}; queued lesson {lesson.title}", kind="qa", viewer=q.user)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("triage: %s", exc)
            await asyncio.sleep(4)

    async def status_loop(self) -> None:
        """A small status file for the progress board (what the hub cannot see from logs)."""
        started = time.strftime("%H:%M:%S")
        while True:
            try:
                sp = getattr(self.speaker, "primary", self.speaker)
                Path("data_cache").mkdir(exist_ok=True)
                Path("data_cache/status.json").write_text(json.dumps({
                    "online_since": started, "voice": f"{getattr(sp, 'engine', 'edge')}:{Path(str(getattr(sp, 'voice', ''))).stem}",
                    "brain": "offline templates" if self.offline else ("paused (limit)" if not brain_available() else "Claude via subscription"),
                    "spend": spend_summary(),
                    "lessons_played": self.lessons_played, "questions_answered": self.questions_answered,
                }))
                await self.send(self._state_msg())      # keeps the console's music toggle and "now playing" current
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(20)

    async def ticker_loop(self) -> None:
        if self.quotes is not None:
            return   # the tick-driven ticker in quotes_loop replaces this
        while True:
            try:
                items = await self.data.ticker(WATCHLIST + (["XAUUSD"] if primary_symbol() == "XAUUSD" else []))
                if items:
                    await self.send({"type": "ticker", "items": items})
            except Exception as exc:  # noqa: BLE001
                log.warning("ticker: %s", exc)
            await asyncio.sleep(60)

    # ------------------------------------------------------------------ main loop
    async def run(self) -> None:
        backoff = 2
        while True:
            try:
                async with websockets.connect(self.hub_url, max_size=2**24) as ws:
                    self.ws = ws
                    backoff = 2
                    tasks = [asyncio.create_task(self._listen()), asyncio.create_task(self.pregen_loop()),
                             asyncio.create_task(self.ticker_loop()), asyncio.create_task(self.chat.run()),
                             asyncio.create_task(self.quotes_loop()), asyncio.create_task(self.triage_loop()), asyncio.create_task(self.status_loop())]
                    try:
                        await self.status(f"director online (offline={self.offline}, voice={'on' if self.speaker else 'captions only'}, memory={'on' if self.memory else 'off'}, chart={primary_symbol()})")
                        try:  # restore the voice chosen in the console last time
                            sp = Path("data_cache/settings.json")
                            if sp.exists():
                                st = json.loads(sp.read_text())
                                await self._set_voice(st.get("engine", "edge"), st.get("voice", ""), False)
                                if st.get("tiktok") and not self.chat.unique_id:
                                    await self.chat.set_username(st["tiktok"])
                                await self.send(self._state_msg())
                        except Exception as exc:  # noqa: BLE001
                            log.warning("voice settings: %s", exc)
                        await self.intro()
                        while True:
                            await self._wait_if_paused()
                            if self.force_market or time.time() - self.last_market_tour > MARKET_TOUR_EVERY_S:
                                await self.market_tour()
                            if time.time() - self.last_ritual > RITUAL_EVERY_S:
                                await self.ritual()
                            if not self.chart_is_live:
                                await self.show_live_chart()
                                await self.send({"type": "mode", "value": "live"})
                            await self.answer_questions(2)
                            try:
                                script = await asyncio.wait_for(self.lesson_queue.get(), timeout=QUIET_INITIATIVE_S[0])
                            except asyncio.TimeoutError:
                                await self.hot_moments()
                                await self.quiet_initiative()
                                await self.social_moments()
                                await self.answer_questions(1)
                                continue
                            await self.status(f"lesson: {script.topic} ({len(script.beats)} beats) · {spend_summary()}")
                            await self.play_lesson(script)
                            await self.show_live_chart()
                            await self.send({"type": "mode", "value": "live"})
                            await self.say(self.picker.pick("bridge"), mood="warm")
                            if self.community.due_between_lessons():
                                await self.say(self.community.line(), mood="warm")
                            await self.social_moments()
                            await self.answer_questions(3, max_rank=2)
                            await self.deliver_promises()
                            await self.hot_moments()
                            self.mood(self.base_mood)
                    finally:
                        for t in tasks:
                            t.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("director loop crashed")
                self.ws = None
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.1f}"
    if p >= 10:
        return f"{p:,.2f}"
    return f"{p:.4f}"


def _spoken(price: float) -> str:
    """Round a price into something comfortable to say."""
    if price >= 10000:
        return f"{round(price, -1):,.0f}"
    if price >= 100:
        return f"{price:,.0f}"
    if price >= 1:
        return f"{price:.2f}"
    return f"{price:.4f}"
