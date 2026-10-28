"""Long-term memory for the teacher.

Backed by Supermemory (SUPERMEMORY_API_KEY) with a local SQLite fallback so the stream
never depends on the network. Writes are fire-and-forget on a background thread; reads
have a short timeout and degrade to the local store.

What gets remembered
- every lesson taught (topic, symbol, the example used, how it was opened)
- every viewer question and the answer (so regulars are recognised and greeted)
- stream events worth a callback later (big market moves during a market tour)
- the teacher's own profile lines (persona facts) so they stay consistent across restarts
"""
from __future__ import annotations

import logging
import os
import queue
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("memory")
NAMESPACE = os.getenv("SUPERMEMORY_NAMESPACE", "chartroom")


class LocalMemory:
    """Tiny keyword-search memory in SQLite (fallback and cache)."""

    def __init__(self, path: str | Path = "data_cache/memory.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute("CREATE TABLE IF NOT EXISTS mem (id INTEGER PRIMARY KEY, ts REAL, kind TEXT, viewer TEXT, text TEXT)")
        self.conn.commit()

    def add(self, text: str, kind: str, viewer: str | None = None) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO mem (ts, kind, viewer, text) VALUES (?,?,?,?)", (time.time(), kind, viewer, text))
            self.conn.commit()

    def search(self, query: str, limit: int = 5, kind: str | None = None, viewer: str | None = None) -> list[str]:
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
        with self.lock:
            sql, args = "SELECT ts, text FROM mem WHERE 1=1", []
            if kind:
                sql += " AND kind=?"; args.append(kind)
            if viewer:
                sql += " AND viewer=?"; args.append(viewer)
            rows = self.conn.execute(sql + " ORDER BY ts DESC LIMIT 400", args).fetchall()
        scored = []
        for ts, text in rows:
            t = text.lower()
            score = sum(1 for w in words if w in t)
            if score or not words:
                scored.append((score, ts, text))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [t for _, _, t in scored[:limit]]

    def recent(self, kind: str, limit: int = 10) -> list[str]:
        with self.lock:
            rows = self.conn.execute("SELECT text FROM mem WHERE kind=? ORDER BY ts DESC LIMIT ?", (kind, limit)).fetchall()
        return [r[0] for r in rows]


class TeacherMemory:
    def __init__(self, api_key: str | None = None, namespace: str = NAMESPACE) -> None:
        self.local = LocalMemory()
        self.namespace = namespace
        self.client = None
        key = api_key if api_key is not None else os.getenv("SUPERMEMORY_API_KEY", "").strip()
        if key:
            try:
                from supermemory import Supermemory

                self.client = Supermemory(api_key=key, timeout=15.0)
                log.info("Supermemory enabled (namespace %s)", namespace)
            except Exception as exc:  # noqa: BLE001
                log.warning("Supermemory unavailable (%s); using local memory only", exc)
        else:
            log.info("SUPERMEMORY_API_KEY not set; using local memory only")
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory")
        self._q: queue.Queue = queue.Queue()
        self.failures = 0
        threading.Thread(target=self._writer, daemon=True).start()

    # ------------------------------------------------------------------ writes
    def remember(self, text: str, kind: str = "event", viewer: str | None = None, meta: dict | None = None, doc_id: str | None = None) -> None:
        """Queue a memory; never blocks the stream."""
        text = " ".join(text.split())
        if not text:
            return
        self.local.add(text, kind, viewer)
        self._q.put((text, kind, viewer, meta or {}, doc_id))

    def _writer(self) -> None:
        while True:
            text, kind, viewer, meta, doc_id = self._q.get()
            if self.client is None:
                continue
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            payload = {"content": f"[{stamp}] ({kind}{' viewer=' + viewer if viewer else ''}) {text}",
                       "metadata": {"kind": kind, **({"viewer": viewer} if viewer else {}), **meta}}
            try:
                if doc_id:
                    self.client.add(self.namespace, id=doc_id, dreaming="instant", **payload)
                else:
                    self.client.add(self.namespace, dreaming="instant", **payload)
                self.failures = 0
            except Exception as exc:  # noqa: BLE001
                self.failures += 1
                if self.failures <= 3 or self.failures % 50 == 0:
                    log.warning("Supermemory add failed (%d): %s", self.failures, exc)

    # ------------------------------------------------------------------ reads
    def _remote_search(self, query: str, limit: int) -> list[str]:
        res = self.client.search(self.namespace, query=query, search_mode="memories", limit=limit)
        out = []
        for r in getattr(res, "results", None) or []:
            txt = getattr(r, "memory", None) or getattr(r, "content", None) or getattr(r, "chunk", None)
            if not txt and isinstance(r, dict):
                txt = r.get("memory") or r.get("content")
            if txt:
                out.append(str(txt))
        return out

    def recall(self, query: str, limit: int = 5, kind: str | None = None, viewer: str | None = None, timeout: float = 4.0) -> list[str]:
        """Best-effort recall: Supermemory first (with timeout), merged with local matches."""
        local = self.local.search(query, limit=limit, kind=kind, viewer=viewer)
        if self.client is None:
            return local
        try:
            fut = self._pool.submit(self._remote_search, query, limit)
            remote = fut.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            log.debug("Supermemory search failed: %s", exc)
            remote = []
        merged, seen = [], set()
        for t in remote + local:
            key = t[:80].lower()
            if key not in seen:
                seen.add(key)
                merged.append(t)
        return merged[:limit]

    def viewer_notes(self, user: str, limit: int = 4) -> list[str]:
        return self.recall(f"viewer {user} asked", limit=limit, viewer=user)

    def recent_lessons(self, limit: int = 12) -> list[str]:
        return self.local.recent("lesson", limit)

    def profile_lines(self, timeout: float = 4.0) -> list[str]:
        """What Supermemory has distilled about the teacher/stream so far."""
        if self.client is None:
            return []
        try:
            prof = self._pool.submit(lambda: self.client.profile(self.namespace)).result(timeout=timeout)
            p = getattr(prof, "profile", prof)
            lines = []
            for group in ("static", "dynamic"):
                for m in getattr(p, group, None) or []:
                    txt = getattr(m, "memory", None) or (m.get("memory") if isinstance(m, dict) else None)
                    if txt:
                        lines.append(str(txt))
            return lines[:20]
        except Exception as exc:  # noqa: BLE001
            log.debug("profile failed: %s", exc)
            return []
