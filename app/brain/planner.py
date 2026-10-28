"""Turns a curriculum lesson into a LessonScript with real chart examples.

Flow: pick symbols/timeframe for the lesson -> scan recent history for genuine
examples of the lesson's pattern -> describe those windows as text -> ask Claude for
the beats -> validate every chart action against the loaded window -> compliance filter.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import anthropic

from ..data.service import DataService, ExampleWindow, DEFAULT_SYMBOLS, iso
from ..data.sources import classify
from ..data.store import TF_SECONDS
from .client import PERSONA, structured
from .curriculum import Curriculum, Lesson
from .deai import clean as deai_clean
from .filters import sanitize
from .schema import TIME_KEYS, Beat, LessonScript, iso_to_unix
from .teaching import arc_description, doctrine, drawing_doctrine, notes_for

log = logging.getLogger("brain")

SCRIPT_RULES = """You are writing the next lesson for the live stream as a JSON LessonScript.

How the stage works
- Each beat has "say" (what you speak, 1-3 short sentences, about 6-14 seconds of speech) and "chart" (a list of actions performed while you speak).
- Start with one "load" action in the FIRST beat using exactly one of the example windows below (copy its symbol, tf, window start and end). The window ENDS NOW: it is the live chart, and the last bar keeps updating while you speak. Say so ("this is live, the last candle is still printing"). Use replay=true so the candles draw in quickly.
- Then, beat by beat, point at what you are describing, with the chartist's tools (see THE DRAWING DOCTRINE): "marker" on the exact bar, "highlight" over a few bars, "hline" at the level/invalidation price, "zone" for an area, "trendline" between two swing points (extend "right" for a ray), "channel" / "regression" / "pitchfork" for the walls of a move, "fib" / "fib_ext" / "fib_fan" on the impulse, "pattern" with its points, neckline and state, "position" as a risk ruler (example only), "measure" for the size of a leg, "vprofile" / "avwap" / "study" for volume and indicators, "session" / "keylevels" / "vline" for context, "alert" on the deciding level, "note" for the written invalidation, "zoom" to tighten the view near the end. Use the exact times (ISO like 2025-09-11T00:00) and prices from the data. Times must be inside the loaded window.
- Give drawings an "id" and reuse it to update them; set "state" (forming / confirmed / invalidated) on patterns and lines and say the state out loud.
- Do not exceed 4 chart actions per beat. Keep text labels short (max 20 chars). A second "load" is allowed later only if you switch to a second example window.
- 9 to 14 beats that follow THE LESSON ARC below, in order. First beat: hook + load. One beat carries "ask" (the check question). Last beat: recap in one breath (takeaway, invalidation, what to watch next).
- Give a one-sentence "summary" (the on-screen takeaway) and a short "quiz" question with its answer.
- Mention risk and invalidation naturally; no targets, no signals, no predictions.
- Non-verbal sounds inline where a person would make them: [chuckles] on a self-deprecating or playful line, [laughs] on a shared win, [sighs] before an honest or painful point, [gasps] at a surprising candle, [groans] at the classic mistake, [clears throat] before the serious point. Two or three per lesson at most, spread out, never in the recap or next to numbers.
"""


def _symbols_for(lesson: Lesson) -> list[str]:
    """Operator rule: gold while the forex market is open, Bitcoin otherwise; the lesson's own
    suggestions only as fallbacks when the primary chart has no example of the pattern."""
    from ..data.market_hours import primary_symbol

    primary = primary_symbol()
    return [primary]        # gold non-stop while forex is open, Bitcoin otherwise; no market hopping for an example


def _validate_actions(script: LessonScript) -> LessonScript:
    """Clamp or drop chart actions that fall outside the currently loaded window."""
    win: tuple[int, int] | None = None
    for beat in script.beats:
        kept = []
        for act in beat.chart:
            a = act.action
            if a == "load":
                win = (iso_to_unix(act.start), iso_to_unix(act.end))
                kept.append(act)
                continue
            if win is None:
                continue  # nothing loaded yet; drop
            lo, hi = win
            ok = True
            times = [getattr(act, k, None) for k in TIME_KEYS]
            for pt in (getattr(act, "points", None) or []):
                if isinstance(pt, dict):
                    times.append(pt.get("time"))
            for v in times:
                if isinstance(v, str):
                    try:
                        t = iso_to_unix(v)
                    except ValueError:
                        ok = False
                        break
                    if not (lo - 1 <= t <= hi + 1):
                        ok = False
                        break
            if ok:
                kept.append(act)
        beat.chart = kept[:4]
    return script


class LessonPlanner:
    def __init__(self, client: anthropic.Anthropic, curriculum: Curriculum, data: DataService, memory=None) -> None:
        self.client = client
        self.curriculum = curriculum
        self.data = data
        self.memory = memory

    def _memory_block(self, lesson: Lesson) -> str:
        """What the teacher said before, so this time is different."""
        if self.memory is None:
            return ""
        try:
            prior = self.memory.recall(f"taught lesson {lesson.title}", limit=3, kind="lesson")
            recent = self.memory.recent_lessons(limit=6)
        except Exception:  # noqa: BLE001
            return ""
        lines = []
        if prior:
            lines.append("YOU HAVE TAUGHT THIS BEFORE. Do not reuse these openings, examples or recaps; find a fresh angle:")
            lines += [f"- {p[:220]}" for p in prior]
        if recent:
            lines.append("YOUR LAST LESSONS ON STREAM (vary your openers, callbacks to these are welcome):")
            lines += [f"- {r[:160]}" for r in recent]
        return "\n".join(lines)

    async def examples_for(self, lesson: Lesson) -> list[ExampleWindow]:
        symbols = _symbols_for(lesson)
        tf = lesson.tf
        wins: list[ExampleWindow] = []
        if lesson.scanner != "none":
            wins = await self.data.find_examples(lesson.scanner, symbols, tf)
            if not wins and tf != "1h":
                wins = await self.data.find_examples(lesson.scanner, symbols, "1h")
        if not wins:
            for s in symbols:
                try:
                    wins.append(await self.data.plain_window(s, tf))
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning("plain window failed for %s: %s", s, exc)
        return wins

    def _prompt(self, lesson: Lesson, wins: list[ExampleWindow]) -> str:
        module = self.curriculum.module(lesson.module)
        parts = [
            f"MODULE: {module.title if module else lesson.module} (level: {module.level if module else 'beginner'})",
            f"TEACHING VOICE FOR THIS MODULE: {module.voice if module else ''}",
            f"LESSON: {lesson.title}\n{lesson.body}",
            "",
            "EXAMPLE WINDOWS FROM REAL MARKET DATA (UTC). Use one of these for the load action and quote its real prices/times:",
        ]
        for i, w in enumerate(wins, 1):
            parts.append(f"--- example {i} ---\n{w.describe()}")
        parts.append("")
        mem = self._memory_block(lesson)
        if mem:
            parts.append(mem)
            parts.append("")
        from ..data.market_hours import session_name

        n = notes_for(lesson.title, lesson.body)
        parts.append("TEACHING NOTES FOR THIS CONCEPT (use the judgement, say it in your own words):\n"
                     f"- plain words: {n.plain}\n- analogy: {n.analogy}\n- the story: {n.story}\n- confirmation: {n.confirm}\n- the mistake: {n.mistake}\n- check question: {n.check}")
        parts.append("")
        parts.append(arc_description())
        parts.append("")
        parts.append(f"Today is {datetime.now(timezone.utc).strftime('%Y-%m-%d')}, it is {session_name()}. Timeframe names allowed: 1m 5m 15m 1h 4h 1d 1w.")
        parts.append("Open the lesson in a way you have not used recently; do not start with 'Let's'. Write the LessonScript JSON now.")
        return "\n".join(parts)

    async def plan(self, lesson: Lesson) -> LessonScript:
        wins = await self.examples_for(lesson)
        if not wins:
            raise RuntimeError(f"no example data available for {lesson.key}")
        user = self._prompt(lesson, wins)
        script = await asyncio.to_thread(
            structured, self.client, LessonScript, system=PERSONA + "\n" + doctrine() + "\n" + drawing_doctrine() + "\n" + SCRIPT_RULES, user=user, effort="high", max_tokens=16000
        )
        script.module = lesson.module
        script = _validate_actions(script)
        cleaned: list[Beat] = []
        for beat in script.beats:
            text, bad = sanitize(deai_clean(beat.say).text)
            if bad:
                log.warning("filtered %s: %s", lesson.key, bad)
            if text.strip():
                beat.say = text
                cleaned.append(beat)
        script.beats = cleaned
        if len(script.beats) < 4:
            raise RuntimeError("lesson too short after filtering")
        return script

    async def plan_topic(self, text: str) -> LessonScript:
        """Operator-injected free-text topic: map to the closest curriculum lesson, else improvise."""
        lesson = self.curriculum.find(text)
        if lesson is None:
            lesson = Lesson(id="custom", title=text[:80], module="custom", body=f"Teach this topic requested by the operator: {text}", scanner="none")
        return await self.plan(lesson)


def window_candles_for_load(data: DataService, symbol: str, tf: str, start: str, end: str):
    """Coroutine used by the director to resolve a load action into candles."""
    return data.get_candles(symbol, tf, iso_to_unix(start), iso_to_unix(end))
