"""Shared contract between the brain (lesson author), the director, and the stage page.

A LessonScript is a list of beats. Each beat is one or two sentences of narration
plus zero or more chart actions that the stage performs while the narration plays.
Only the actions defined here exist; the stage ignores anything else.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d", "1w"]


State = Literal["forming", "confirmed", "invalidated"]


class Drawing(BaseModel):
    """Base for every drawing. `id`: redrawing with the same id replaces the old object instead of stacking a duplicate.
    `state`: forming = dashed (still printing), confirmed = solid, invalidated = greyed with a cross (kept on screen as the honest record)."""
    id: str | None = Field(default=None, max_length=24, description="stable name, e.g. trend1; reuse it to update the same drawing")
    state: State | None = None


class LoadAction(BaseModel):
    """Load a symbol/timeframe/date window. With replay=True the bars appear one by one."""
    action: Literal["load"] = "load"
    symbol: str = Field(description="e.g. BTCUSDT, EURUSD, AAPL")
    tf: Timeframe
    start: str = Field(description="ISO date or datetime (UTC), e.g. 2025-09-01")
    end: str = Field(description="ISO date or datetime (UTC), exclusive")
    replay: bool = True
    pace_ms: int = Field(default=90, ge=20, le=1000, description="ms between replayed bars")


class MarkerAction(Drawing):
    """Put a labelled arrow/circle on one bar."""
    action: Literal["marker"] = "marker"
    time: str
    text: str = Field(max_length=24)
    position: Literal["aboveBar", "belowBar"] = "belowBar"
    shape: Literal["arrowUp", "arrowDown", "circle", "square"] = "arrowUp"
    color: str = "#f5c542"


class HighlightAction(Drawing):
    """Shade a time range (used to spotlight a pattern)."""
    action: Literal["highlight"] = "highlight"
    start: str
    end: str
    color: str = "rgba(245,197,66,0.18)"
    label: str | None = Field(default=None, max_length=24)


class HLineAction(Drawing):
    """Horizontal price line, e.g. support, resistance, invalidation, target."""
    action: Literal["hline"] = "hline"
    price: float
    label: str = Field(max_length=24)
    color: str = "#4fd1c5"
    style: Literal["solid", "dashed", "dotted"] = "dashed"


class TrendlineAction(Drawing):
    """Straight line between two (time, price) points."""
    action: Literal["trendline"] = "trendline"
    t1: str
    p1: float
    t2: str
    p2: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "#f56565"
    extend: bool | Literal["none", "right", "both"] = Field(default=False, description="right = ray (extends to the right edge), both = extended line")


class ZoneAction(Drawing):
    """Horizontal band between two prices (support/resistance zone)."""
    action: Literal["zone"] = "zone"
    top: float
    bottom: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "rgba(79,209,197,0.22)"


class RectAction(Drawing):
    """Box in time and price (order block, fair value gap, consolidation)."""
    action: Literal["rect"] = "rect"
    t1: str
    t2: str
    top: float
    bottom: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "rgba(167,139,250,0.25)"


class FibAction(Drawing):
    """Fibonacci retracement between two swing points."""
    action: Literal["fib"] = "fib"
    t1: str
    p1: float
    t2: str
    p2: float
    levels: list[float] = Field(default_factory=lambda: [0.382, 0.5, 0.618, 0.786])
    color: str = "#a78bfa"


class PathAction(Drawing):
    """Polyline through (time, price) points (structure zig-zag, pattern outline)."""
    action: Literal["path"] = "path"
    points: list[dict] = Field(description="[{time: ISO, price: float}, ...] at least 2 points")
    color: str = "#f5c542"
    width: int = 2
    dashed: bool = False
    label: str | None = Field(default=None, max_length=24)
    labels: list[str] | None = Field(default=None, description="one short label per point, e.g. 1 2 3 4 5 or A B C D")


class ArrowAction(Drawing):
    """Arrow from one point to another (measured move, projection, impulse)."""
    action: Literal["arrow"] = "arrow"
    t1: str
    p1: float
    t2: str
    p2: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "#e879f9"


class NoteAction(Drawing):
    """Handwritten-style note anchored at (time, price)."""
    action: Literal["note"] = "note"
    time: str
    price: float
    text: str = Field(max_length=80)
    color: str = "#f5c542"


class IndicatorAction(Drawing):
    """Overlay line indicator (EMA/VWAP) given as explicit points."""
    action: Literal["indicator"] = "indicator"
    name: str = Field(max_length=16)
    points: list[dict] = Field(description="[{time: ISO, value: float}, ...]")
    color: str = "#38bdf8"


class VLineAction(Drawing):
    """Vertical time line (session open, news release, the anchor bar of an analysis)."""
    action: Literal["vline"] = "vline"
    time: str
    label: str | None = Field(default=None, max_length=24)
    color: str = "#787b86"
    style: Literal["solid", "dashed", "dotted"] = "dashed"


class ChannelAction(Drawing):
    """Parallel channel: base line t1/p1 -> t2/p2 and a parallel line through t3/p3 (the opposite swing)."""
    action: Literal["channel"] = "channel"
    t1: str
    p1: float
    t2: str
    p2: float
    t3: str
    p3: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "#2962ff"
    extend: bool = True


class RegressionAction(Drawing):
    """Linear regression channel over a time range (midline + bands at k standard deviations), computed from the candles on screen."""
    action: Literal["regression"] = "regression"
    start: str
    end: str
    deviations: float = Field(default=2.0, ge=0.5, le=4.0)
    label: str | None = Field(default=None, max_length=24)
    color: str = "#2962ff"


class PitchforkAction(Drawing):
    """Andrews pitchfork from three pivots: handle at t1/p1, tines through the midpoint of t2/p2 and t3/p3."""
    action: Literal["pitchfork"] = "pitchfork"
    t1: str
    p1: float
    t2: str
    p2: float
    t3: str
    p3: float
    label: str | None = Field(default=None, max_length=24)
    color: str = "#f23645"


class FibExtAction(Drawing):
    """Fibonacci extension from an impulse A (t1/p1) -> B (t2/p2) and the pullback end C (t3/p3)."""
    action: Literal["fib_ext"] = "fib_ext"
    t1: str
    p1: float
    t2: str
    p2: float
    t3: str
    p3: float
    levels: list[float] = Field(default_factory=lambda: [0.618, 1.0, 1.272, 1.618, 2.0])
    color: str = "#a78bfa"


class FibFanAction(Drawing):
    """Fibonacci fan: speed lines from t1/p1 through the 0.382/0.5/0.618 retracement points of the leg to t2/p2."""
    action: Literal["fib_fan"] = "fib_fan"
    t1: str
    p1: float
    t2: str
    p2: float
    levels: list[float] = Field(default_factory=lambda: [0.382, 0.5, 0.618])
    color: str = "#a78bfa"


class PositionAction(Drawing):
    """Long / short position tool: entry, stop (invalidation) and target with the risk-reward ratio. Teaching only; it is a ruler, never a signal."""
    action: Literal["position"] = "position"
    side: Literal["long", "short"]
    time: str = Field(description="bar where the box starts")
    entry: float
    stop: float
    target: float
    risk_pct: float = Field(default=1.0, ge=0.1, le=5.0, description="account risk the example assumes")
    label: str | None = Field(default=None, max_length=24)


class MeasureAction(Drawing):
    """Price / date range ruler between two points: shows the price change, percent and number of bars."""
    action: Literal["measure"] = "measure"
    t1: str
    p1: float
    t2: str
    p2: float


class VProfileAction(Drawing):
    """Fixed-range volume profile over start..end with point of control and value area (70%), computed from the candles on screen."""
    action: Literal["vprofile"] = "vprofile"
    start: str
    end: str
    rows: int = Field(default=24, ge=8, le=60)
    label: str | None = Field(default=None, max_length=24)


class AVwapAction(Drawing):
    """Anchored VWAP from an anchor bar forward (swing, session open, news bar)."""
    action: Literal["avwap"] = "avwap"
    anchor: str
    label: str | None = Field(default=None, max_length=24)
    color: str = "#ff9800"


class StudyAction(Drawing):
    """Built-in indicator computed on the stage: overlays (ema, sma, bollinger, vwap) or a pane below the candles (rsi, macd, atr)."""
    action: Literal["study"] = "study"
    kind: Literal["ema", "sma", "bollinger", "vwap", "rsi", "macd", "atr"]
    length: int = Field(default=20, ge=2, le=400)
    mult: float = Field(default=2.0, ge=0.5, le=4.0, description="bollinger deviations")
    fast: int = Field(default=12, ge=2, le=100)
    slow: int = Field(default=26, ge=3, le=200)
    signal: int = Field(default=9, ge=2, le=50)
    color: str = "#2962ff"


class PatternAction(Drawing):
    """Chart pattern outline with a state: corners as points, an optional neckline / breakout level, and the label."""
    action: Literal["pattern"] = "pattern"
    kind: Literal["triangle", "wedge", "flag", "head_shoulders", "inv_head_shoulders", "double_top", "double_bottom", "cup_handle", "rectangle", "channel", "harmonic", "elliott", "other"]
    points: list[dict] = Field(description="[{time: ISO, price: float}, ...] corners in time order, 3 to 9 points")
    neckline: float | None = Field(default=None, description="the level whose close confirms the pattern")
    labels: list[str] | None = Field(default=None, description="optional per-corner labels (LS, H, RS; 1-5; X A B C D)")
    label: str | None = Field(default=None, max_length=24)
    color: str = "#e879f9"


class AlertAction(Drawing):
    """Price alert line: the stage flashes it and tells the host when the live price crosses it."""
    action: Literal["alert"] = "alert"
    price: float
    label: str = Field(max_length=24)
    color: str = "#f23645"


class SessionAction(Drawing):
    """Shade a trading session on the chart and draw its high and low (asia, london, newyork, or a custom start..end)."""
    action: Literal["session"] = "session"
    name: Literal["asia", "london", "newyork", "custom"] = "london"
    start: str | None = None
    end: str | None = None
    levels: bool = True


class KeyLevelsAction(Drawing):
    """Higher-timeframe reference levels from the loaded history: previous day/week high, low, open and the current day open."""
    action: Literal["keylevels"] = "keylevels"
    which: list[Literal["pdh", "pdl", "pdo", "pwh", "pwl", "dopen", "wopen"]] = Field(default_factory=lambda: ["pdh", "pdl", "dopen"])
    color: str = "#787b86"


class RemoveAction(BaseModel):
    """Remove one drawing by id (or set its state instead of removing it, to keep the record honest)."""
    action: Literal["remove"] = "remove"
    id: str = Field(max_length=24)
    state: State | None = Field(default=None, description="when given, the drawing is restyled to this state instead of removed")


class ZoomAction(BaseModel):
    """Set the visible time range."""
    action: Literal["zoom"] = "zoom"
    start: str
    end: str


class ClearAction(BaseModel):
    """Remove markers, highlights, lines and trendlines (keeps the candles)."""
    action: Literal["clear"] = "clear"


ChartAction = Annotated[
    Union[LoadAction, MarkerAction, HighlightAction, HLineAction, TrendlineAction, ZoneAction, RectAction, FibAction, PathAction, ArrowAction, NoteAction, IndicatorAction,
          VLineAction, ChannelAction, RegressionAction, PitchforkAction, FibExtAction, FibFanAction, PositionAction, MeasureAction, VProfileAction, AVwapAction, StudyAction,
          PatternAction, AlertAction, SessionAction, KeyLevelsAction, RemoveAction, ZoomAction, ClearAction],
    Field(discriminator="action"),
]


class Beat(BaseModel):
    say: str = Field(description="One to three short spoken sentences. Conversational, no bullet points.")
    chart: list[ChartAction] = Field(default_factory=list)
    deep: bool = Field(default=False, description="true to run the full draft-book analysis pass on the loaded chart during this beat")
    pause_ms: int = Field(default=350, ge=0, le=5000, description="silence after the narration")
    ask: str = Field(default="", max_length=200, description="One answerable question for the chat (A/B or yes/no style). The stream opens an answer window after this beat. Use it exactly once per lesson, at the 'check' step.")

    # the model occasionally overshoots a bound; clamp instead of throwing away a whole lesson
    @field_validator("pause_ms", mode="before")
    @classmethod
    def _clamp_pause(cls, v):
        try:
            return int(min(max(float(v), 0), 5000))
        except (TypeError, ValueError):
            return 350

    @field_validator("ask", mode="before")
    @classmethod
    def _trim_ask(cls, v):
        return (v or "")[:200] if isinstance(v, str) else ""


class Quiz(BaseModel):
    question: str
    answer: str


class LessonScript(BaseModel):
    topic: str = Field(max_length=80)
    module: str = Field(description="curriculum module id, e.g. candlesticks")
    summary: str = Field(max_length=300, description="one-sentence takeaway shown on screen")
    beats: list[Beat] = Field(min_length=4, max_length=40)
    quiz: Quiz | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _trim_topic(cls, v):
        return v[:80] if isinstance(v, str) else v

    @field_validator("summary", mode="before")
    @classmethod
    def _trim_summary(cls, v):
        return v[:300] if isinstance(v, str) else v

    @field_validator("beats", mode="before")
    @classmethod
    def _cap_beats(cls, v):
        return v[:40] if isinstance(v, list) else v


class ChatReply(BaseModel):
    """What the brain says back to a viewer question (empty say = choose silence)."""
    say: str = Field(max_length=700, description="Spoken words only; empty string means wait and say nothing")
    answered: bool = Field(description="False when the question was off-topic or unsafe and was deflected")
    delivery: Literal["warm", "calm", "curious", "amused", "focused", "cheerful", "excited", "considerate", "none"] = Field(default="warm", description="How to deliver it")
    follow_up: str | None = Field(default=None, description="A concrete thing you just promised to show or explain later, or null")


TIME_KEYS = ("time", "start", "end", "t1", "t2", "t3", "anchor")


def convert_times(d: dict) -> dict:
    """ISO strings -> unix seconds on every time-bearing field of a chart action dict (in place, returned)."""
    for k in TIME_KEYS:
        if isinstance(d.get(k), str):
            d[k] = iso_to_unix(d[k])
    if isinstance(d.get("points"), list):
        for pt in d["points"]:
            if isinstance(pt, dict) and isinstance(pt.get("time"), str):
                pt["time"] = iso_to_unix(pt["time"])
    return d


def iso_to_unix(value: str) -> int:
    """Parse an ISO date/datetime (assumed UTC when naive) to unix seconds."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
