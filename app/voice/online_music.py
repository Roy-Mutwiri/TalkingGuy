"""Online music source for the bed: what is trending right now on Audius.

Audius is an open music platform: artists upload their own tracks and its public API (no key) serves a trending
chart and a stream URL per track, which is how third-party players are meant to use it. That makes it the
"popular songs from the internet" source that does not get a TikTok LIVE muted: nothing here is a commercial
label release, so there is nothing for the fingerprint to match (see TIKTOK_RULES.md section 2).

Remixes, edits, bootlegs, mashups and covers of other songs are skipped by title, because a remix of a known song
is still that song's composition and would be matched.

    src = OnlineMusic()
    path, label = src.next_file()      # downloads the next trending track into data_cache/online_music/, returns it

Chart: tuned to hip-hop and afrobeats. Two sources, interleaved one after the other: the Hip-Hop/Rap trending
chart of the week in chart order (most popular first), and the most-played tracks found by searching afrobeats /
afrobeat / amapiano / afropop (Audius has no afrobeats chart). Re-fetched every 15 minutes so a track that climbs
is picked up within the quarter hour; the same track is not repeated until the list has been played through.
Change the mix with MUSIC_ONLINE_GENRES (comma list of Audius trending genres) and MUSIC_ONLINE_SEARCH (comma list
of search words) in .env. Downloads keep at most KEEP_FILES files in the cache.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger("music")

API_ROOT = "https://api.audius.co"
APP_NAME = "chartroom"
CHART_LIMIT = 100
REFRESH_S = 15 * 60                   # real-time enough: the chart itself moves over hours
MIN_S, MAX_S = 75, 540                # skip jingles and very long mixes
KEEP_FILES = 12
SKIP_TITLE = re.compile(r"\b(remix|rmx|edit|bootleg|mashup|mash-up|cover|flip|rework|re-work|mix|sped.?up|speed.?up|slowed|nightcore|snippet|snipet|preview|teaser|intro|episode|type beat|instrumental)\b", re.I)
# search hits (afrobeats side) must really be afro music and in a fitting genre; the search itself is fuzzy
AFRO_WORDS = re.compile(r"afro|amapiano|naija|highlife|hiplife|alt[eé]|lagos|nigeria|ghana|kenya|south ?africa", re.I)
SEARCH_GENRES = {"Hip-Hop/Rap", "World", "Afrobeats", "R&B/Soul", "Pop", "Electronic", "House", "Dancehall", "Trap", "Lo-Fi"}
GENRES = [g.strip() for g in os.getenv("MUSIC_ONLINE_GENRES", "Hip-Hop/Rap").split(",") if g.strip()]
SEARCHES = [q.strip() for q in os.getenv("MUSIC_ONLINE_SEARCH", "afrobeats,afrobeat,amapiano,afropop").split(",") if q.strip()]


class OnlineMusic:
    def __init__(self, cache_dir: str | Path = "data_cache/online_music", time_range: str = "week") -> None:
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.time_range = time_range
        self._hosts: list[str] = []
        self._queue: list[dict] = []
        self._played: set[str] = set()
        self._refreshed = 0.0
        self._lock = threading.Lock()
        self._client = httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True,
                                    headers={"User-Agent": "ChartRoom music bed (chartroom)"})

    # ---- discovery -------------------------------------------------------------
    def _host(self) -> str:
        if not self._hosts:
            try:
                r = self._client.get(API_ROOT, timeout=15.0)
                r.raise_for_status()
                data = r.json().get("data") or []
                self._hosts = [h.rstrip("/") for h in data if isinstance(h, str)] or [API_ROOT]
            except Exception as exc:  # noqa: BLE001
                log.warning("online music: host discovery failed (%s); using %s", exc, API_ROOT)
                self._hosts = [API_ROOT]
        return random.choice(self._hosts)

    @staticmethod
    def _ok(t: dict, search_hit: bool = False) -> bool:
        title = str(t.get("title") or "")
        dur = int(t.get("duration") or 0)
        if not (t.get("id") and t.get("is_streamable", True) and MIN_S <= dur <= MAX_S and not SKIP_TITLE.search(title)):
            return False
        if search_hit:
            blob = " ".join(str(t.get(k) or "") for k in ("title", "tags", "genre", "description"))
            return str(t.get("genre") or "") in SEARCH_GENRES and bool(AFRO_WORDS.search(blob))
        return True

    def _trending(self, host: str, genre: str | None) -> list[dict]:
        params = {"app_name": APP_NAME, "time": self.time_range, "limit": CHART_LIMIT}
        if genre:
            params["genre"] = genre
        r = self._client.get(f"{host}/v1/tracks/trending", params=params, timeout=30.0)
        r.raise_for_status()
        return [t for t in (r.json().get("data") or []) if self._ok(t)]

    def _search(self, host: str, query: str) -> list[dict]:
        r = self._client.get(f"{host}/v1/tracks/search", params={"app_name": APP_NAME, "query": query, "limit": 100}, timeout=30.0)
        r.raise_for_status()
        return [t for t in (r.json().get("data") or []) if self._ok(t, search_hit=True)]

    @staticmethod
    def _interleave(lists: list[list[dict]]) -> list[dict]:
        out, seen = [], set()
        for i in range(max((len(l) for l in lists), default=0)):
            for l in lists:
                if i < len(l) and l[i]["id"] not in seen:
                    seen.add(l[i]["id"])
                    out.append(l[i])
        return out

    def refresh(self) -> int:
        """Fetch the tuned chart (genre trending lists + most-played search hits, interleaved). Returns the queue size."""
        host = self._host()
        lists: list[list[dict]] = []
        for g in GENRES:
            try:
                lists.append(self._trending(host, g))
            except Exception as exc:  # noqa: BLE001
                log.warning("online music: trending %s failed (%s)", g, exc)
        if SEARCHES:
            hits: dict[str, dict] = {}
            for q in SEARCHES:
                try:
                    for t in self._search(host, q):
                        hits.setdefault(t["id"], t)
                except Exception as exc:  # noqa: BLE001
                    log.warning("online music: search %s failed (%s)", q, exc)
            lists.append(sorted(hits.values(), key=lambda t: -int(t.get("play_count") or 0)))
        tracks = self._interleave(lists)
        if not tracks and not GENRES:
            tracks = self._trending(host, None)
        fresh = [t for t in tracks if t["id"] not in self._played]
        if not fresh:                        # everything has been played: start over
            self._played.clear()
            fresh = tracks
        with self._lock:                    # most popular unplayed track of each source, alternating
            self._queue = fresh
            self._refreshed = time.time()
        log.info("online music: %d tracks queued (%s + search %s)", len(fresh), "/".join(GENRES) or "all genres", ",".join(SEARCHES) or "none")
        return len(fresh)

    # ---- files -----------------------------------------------------------------
    def _prune(self) -> None:
        files = sorted(self.cache.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        for p in files[:-KEEP_FILES]:
            try:
                p.unlink()
            except OSError:
                pass

    def next_file(self) -> tuple[Path, str] | None:
        """Download the next trending track and return (path, label), or None when nothing could be fetched."""
        for attempt in range(4):
            with self._lock:
                stale = time.time() - self._refreshed > REFRESH_S
                track = self._queue.pop(0) if self._queue and not stale else None
            if track is None:
                try:
                    if not self.refresh():
                        return None
                except Exception as exc:  # noqa: BLE001
                    log.warning("online music: chart fetch failed (%s)", exc)
                    time.sleep(2 + attempt * 3)
                    continue
                continue
            tid = str(track["id"])
            artist = str((track.get("user") or {}).get("name") or "unknown artist")
            title = str(track.get("title") or tid)
            label = f"{title} - {artist} (Audius)"
            path = self.cache / f"{tid}.mp3"
            if path.exists() and path.stat().st_size > 200_000:
                self._played.add(tid)
                return path, label
            try:
                url = f"{self._host()}/v1/tracks/{tid}/stream"
                tmp = path.with_suffix(".part")
                with self._client.stream("GET", url, params={"app_name": APP_NAME}) as r:
                    r.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes(1 << 16):
                            f.write(chunk)
                if tmp.stat().st_size < 200_000:
                    raise RuntimeError("stream too short")
                tmp.replace(path)
                (self.cache / f"{tid}.json").write_text(json.dumps({"id": tid, "title": title, "artist": artist,
                                                                       "permalink": track.get("permalink"), "genre": track.get("genre")}), encoding="utf-8")
                self._played.add(tid)
                self._prune()
                return path, label
            except Exception as exc:  # noqa: BLE001
                log.warning("online music: download failed for %s (%s)", label, exc)
                time.sleep(1)
        return None
