"""Loads the curriculum markdown files in app/brain/curriculum/.

File format (see any module file):
    ---
    module: candlesticks
    title: Candlesticks & price action
    level: beginner
    ---
    # Title
    ## Teaching voice
    ...paragraph...
    ## Lessons
    ### lesson_id: Lesson title
    - key points: ...
    - pattern_scanner: engulfing_bull
    - on_screen_takeaway: ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CURRICULUM_DIR = Path(__file__).resolve().parent / "curriculum"
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_LESSON = re.compile(r"^###\s+([a-z0-9_]+)\s*:\s*(.+?)\s*$", re.M)
_SCANNER = re.compile(r"pattern_scanner\s*:\s*`?([a-z_]+)`?", re.I)
_TAKEAWAY = re.compile(r"on_screen_takeaway\s*:\s*(.+)", re.I)
_EXAMPLE = re.compile(r"best example\s*:\s*(.+)", re.I)
_SYMBOL = re.compile(r"\b(BTCUSDT|ETHUSDT|SOLUSDT|EURUSD|GBPUSD|USDJPY|XAUUSD|AAPL|NVDA|MSFT|SPY|TSLA)\b")
_TF = re.compile(r"\b(15m|1h|4h|1d)\b")


@dataclass
class Lesson:
    id: str
    title: str
    module: str
    body: str                      # raw markdown of the lesson block
    scanner: str = "none"
    takeaway: str = ""
    symbols: list[str] = field(default_factory=list)
    tf: str = "4h"

    @property
    def key(self) -> str:
        return f"{self.module}/{self.id}"


@dataclass
class Module:
    id: str
    title: str
    level: str
    voice: str
    lessons: list[Lesson]


def _parse_module(text: str, fallback_id: str) -> Module:
    meta: dict[str, str] = {}
    m = _FRONT.match(text)
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = text[m.end():]
    mid = meta.get("module", fallback_id)
    voice = ""
    vm = re.search(r"##\s*Teaching voice\s*\n(.*?)(?=\n##\s|\Z)", body, re.S)
    if vm:
        voice = " ".join(vm.group(1).split())
    lessons: list[Lesson] = []
    matches = list(_LESSON.finditer(body))
    for i, lm in enumerate(matches):
        start = lm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end].strip()
        sc = _SCANNER.search(block)
        tk = _TAKEAWAY.search(block)
        ex = _EXAMPLE.search(block)
        symbols = _SYMBOL.findall(ex.group(1)) if ex else []
        tfm = _TF.search(ex.group(1)) if ex else None
        lessons.append(Lesson(
            id=lm.group(1), title=lm.group(2).strip(), module=mid, body=block,
            scanner=(sc.group(1).lower() if sc else "none"),
            takeaway=(tk.group(1).strip().strip("*_") if tk else ""),
            symbols=symbols or [], tf=(tfm.group(1) if tfm else "4h"),
        ))
    return Module(id=mid, title=meta.get("title", mid), level=meta.get("level", "beginner"), voice=voice, lessons=lessons)


class Curriculum:
    def __init__(self, directory: Path | str = CURRICULUM_DIR) -> None:
        self.dir = Path(directory)
        self.modules: list[Module] = []
        for p in sorted(self.dir.glob("*.md")):
            self.modules.append(_parse_module(p.read_text(encoding="utf-8"), p.stem.split("_", 1)[-1]))

    @property
    def lessons(self) -> list[Lesson]:
        return [l for m in self.modules for l in m.lessons]

    def module(self, mid: str) -> Module | None:
        return next((m for m in self.modules if m.id == mid), None)

    def get(self, key: str) -> Lesson | None:
        return next((l for l in self.lessons if l.key == key or l.id == key), None)

    STOP = {"the", "a", "an", "on", "of", "and", "in", "to", "for", "with", "is", "it", "at", "how", "do", "does", "why", "what", "can", "you",
            "please", "me", "my", "i", "we", "about", "explain", "teach", "lesson", "trading", "trade", "chart", "market", "price", "gold", "bitcoin", "btc", "xau"}

    def find(self, text: str) -> Lesson | None:
        """Match a topic phrase to a lesson. Title/id words count triple; a plain body overlap alone
        is not enough, so 'why does gold spike at the london open' does not land on a random lesson."""
        words = set(re.findall(r"[a-z]+", text.lower())) - self.STOP
        words = {w for w in words if len(w) > 2}
        if not words:
            return None
        best, score = None, 0.0
        for l in self.lessons:
            title_words = set(re.findall(r"[a-z]+", (l.id.replace("_", " ") + " " + l.title).lower())) - self.STOP
            body_words = set(re.findall(r"[a-z]+", l.body[:400].lower())) - self.STOP
            s = 3 * len(words & title_words) + len(words & body_words)
            if s > score:
                best, score = l, s
        if best is None:
            return None
        title_hit = bool(words & (set(re.findall(r"[a-z]+", (best.id.replace("_", " ") + " " + best.title).lower())) - self.STOP))
        return best if (title_hit or score >= 4) else None

    def overview(self) -> str:
        """Short syllabus text for prompts."""
        lines = []
        for m in self.modules:
            lines.append(f"- {m.id} ({m.level}): " + "; ".join(l.title for l in m.lessons))
        return "\n".join(lines)
