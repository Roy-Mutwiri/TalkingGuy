"""Reads TikTok LIVE chat with the TikTokLive library.

Comments go through a cheap pre-filter (profanity, links, duplicates, per-user cooldown),
then into a pending list that the director triages in batches (priority high/medium/low/spam,
plus a lesson topic when someone asks to learn something). Prioritised questions wait in a
heap; the director pulls the best one whenever it has a moment.

Social events (join/follow/gift/like/share) go to a separate queue. The username can be
changed at runtime from the operator console; the reader reconnects.
"""
from __future__ import annotations

import asyncio
import heapq
import logging
import os
import time
from dataclasses import dataclass, field

from .moderation import Moderator, Question
from .triage import RANK

log = logging.getLogger("chat")


@dataclass(order=True)
class Ranked:
    rank: int
    ts: float
    q: Question = field(compare=False)
    topic: str | None = field(default=None, compare=False)


class ChatReader:
    def __init__(self, unique_id: str | None = None, moderator: Moderator | None = None) -> None:
        self.unique_id = (unique_id or os.getenv("TIKTOK_UNIQUE_ID", "")).lstrip("@").strip()
        self.mod = moderator or Moderator()
        self.events: asyncio.Queue[tuple[str, str, dict]] = asyncio.Queue(maxsize=200)
        self.pending: list[Question] = []          # waiting for triage
        self.heap: list[Ranked] = []               # triaged, best first
        self.connected = False
        self.viewers = 0
        self.comments_seen = 0
        self.answered = 0
        self._client = None
        self._restart = asyncio.Event()
        self.last_error = ""
        self.answer_sink: list[tuple[str, str]] | None = None   # open while the host waits for answers to a question

    # ------------------------------------------------------------------ intake
    def offer(self, user: str, text: str) -> None:
        """Pre-filter a comment and park it for triage (also used by the operator console)."""
        if self.answer_sink is not None and 0 < len(text.strip()) <= 40 and "?" not in text:
            if len(self.answer_sink) < 60:
                self.answer_sink.append((str(user)[:30], text.strip()))
            return
        q = self.mod.assess(user, text)
        if q is None:
            return
        self.pending.append(q)
        del self.pending[:-40]

    def take_pending(self, n: int = 15) -> list[Question]:
        batch, self.pending = self.pending[:n], self.pending[n:]
        return batch

    def push(self, q: Question, priority: str, topic: str | None = None) -> None:
        if priority == "spam":
            return
        heapq.heappush(self.heap, Ranked(RANK.get(priority, 2), q.ts, q, topic))
        if len(self.heap) > 30:            # drop the worst
            self.heap.sort()
            del self.heap[30:]
            heapq.heapify(self.heap)

    def pop(self, max_rank: int = 2, max_age_s: float = 600) -> Ranked | None:
        """Best question with rank <= max_rank; stale ones are discarded."""
        now = time.time()
        while self.heap:
            if self.heap[0].rank > max_rank:
                return None
            r = heapq.heappop(self.heap)
            if now - r.ts > max_age_s and r.rank > 0:
                continue
            return r
        return None

    def event(self, kind: str, user: str, **extra) -> None:
        if self.events.full():
            try:
                self.events.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.events.put_nowait((kind, str(user)[:30], extra))

    # ------------------------------------------------------------------ connection
    async def set_username(self, name: str) -> None:
        name = (name or "").lstrip("@").strip()
        if not name or name == self.unique_id:
            return
        self.unique_id = name
        log.info("chat: switching to @%s", name)
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._restart.set()

    async def run(self) -> None:
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, RoomUserSeqEvent, JoinEvent, FollowEvent, GiftEvent, LikeEvent, ShareEvent
        except Exception as exc:  # noqa: BLE001
            log.warning("TikTokLive not available: %s", exc)
            return

        while True:
            self._restart.clear()
            if not self.unique_id:
                await asyncio.sleep(2)
                continue
            client = TikTokLiveClient(unique_id=f"@{self.unique_id}")
            self._client = client

            @client.on(ConnectEvent)
            async def on_connect(_e):
                self.connected = True
                self.last_error = ""
                log.info("chat connected to @%s", self.unique_id)

            @client.on(DisconnectEvent)
            async def on_disconnect(_e):
                self.connected = False
                log.info("chat disconnected")

            @client.on(CommentEvent)
            async def on_comment(e: CommentEvent):
                self.comments_seen += 1
                user = getattr(e.user, "nickname", None) or getattr(e.user, "unique_id", "viewer")
                self.offer(str(user)[:30], e.comment or "")

            @client.on(RoomUserSeqEvent)
            async def on_viewers(e):
                self.viewers = getattr(e, "total", self.viewers) or self.viewers

            def _name(e):
                u = getattr(e, "user", None)
                return (getattr(u, "nickname", None) or getattr(u, "unique_id", None) or "someone") if u else "someone"

            @client.on(JoinEvent)
            async def on_join(e):
                self.event("join", _name(e))

            @client.on(FollowEvent)
            async def on_follow(e):
                self.event("follow", _name(e))

            @client.on(ShareEvent)
            async def on_share(e):
                self.event("share", _name(e))

            @client.on(LikeEvent)
            async def on_like(e):
                self.event("like", _name(e), count=getattr(e, "count", 1) or 1)

            @client.on(GiftEvent)
            async def on_gift(e):
                g = getattr(e, "gift", None)
                if bool(getattr(g, "streakable", False)) and bool(getattr(e, "streaking", False)):
                    return
                self.event("gift", _name(e), gift=getattr(g, "name", "a gift"), count=getattr(e, "repeat_count", 1) or 1)

            try:
                live = await client.is_live()
                if not live:
                    self.last_error = f"@{self.unique_id} is not live yet"
                    log.info("%s; retrying in 20s", self.last_error)
                    for _ in range(20):
                        if self._restart.is_set():
                            break
                        await asyncio.sleep(1)
                    continue
                await client.connect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:160]
                self.connected = False
                log.warning("chat reader error: %s; reconnecting in 15s", self.last_error)
                for _ in range(15):
                    if self._restart.is_set():
                        break
                    await asyncio.sleep(1)
            else:
                self.connected = False
                await asyncio.sleep(3)
