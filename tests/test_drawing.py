"""The expanded drawing vocabulary: schema, scanners, the draft-book analysis, the doctrine and curriculum."""
import json
import math
import random

from app.brain.curriculum import Curriculum
from app.brain.schema import (AlertAction, Beat, ChannelAction, FibExtAction, KeyLevelsAction, LessonScript, PatternAction, PositionAction,
                              RegressionAction, RemoveAction, SessionAction, StudyAction, TrendlineAction, VProfileAction, convert_times)
from app.brain.teaching import drawing_doctrine, notes_for
from app.data import patterns
from app.data.analysis import analyze


def _series(n=300, seed=3):
    rnd = random.Random(seed)
    out, p, t = [], 2000.0, 1_700_000_000
    for i in range(n):
        o = p
        c = o + math.sin(i / 23) * 2.5 + rnd.gauss(0, 3)
        h = max(o, c) + abs(rnd.gauss(0, 2))
        lo = min(o, c) - abs(rnd.gauss(0, 2))
        out.append({"time": t + i * 900, "open": o, "high": h, "low": lo, "close": c, "volume": 100 + rnd.random() * 50})
        p = c
    return out


def test_new_actions_validate_and_convert():
    script = LessonScript(topic="t", module="m", summary="s", beats=[
        Beat(say="a", chart=[TrendlineAction(id="t1", t1="2025-01-01T00:00", p1=1, t2="2025-01-02T00:00", p2=2, extend="right", state="forming")]),
        Beat(say="b", chart=[ChannelAction(t1="2025-01-01", p1=1, t2="2025-01-02", p2=2, t3="2025-01-01T12:00", p3=0.5),
                             PositionAction(side="long", time="2025-01-02", entry=100, stop=95, target=115),
                             PatternAction(id="pat", kind="double_top", points=[{"time": "2025-01-01", "price": 2}, {"time": "2025-01-01T12:00", "price": 1}, {"time": "2025-01-02", "price": 2}], neckline=1.0, state="forming")]),
        Beat(say="c", chart=[RegressionAction(start="2025-01-01", end="2025-01-02"), VProfileAction(start="2025-01-01", end="2025-01-02"), StudyAction(kind="rsi", length=14), SessionAction(name="london")]),
        Beat(say="d", chart=[AlertAction(price=101.5, label="PDH"), KeyLevelsAction(which=["pdh", "pdl"]), FibExtAction(t1="2025-01-01", p1=1, t2="2025-01-02", p2=2, t3="2025-01-02T06:00", p3=1.5), RemoveAction(id="pat", state="invalidated")]),
    ])
    d = convert_times(script.beats[1].chart[2].model_dump())
    assert isinstance(d["points"][0]["time"], int)
    d2 = convert_times(script.beats[3].chart[2].model_dump())
    assert all(isinstance(d2[k], int) for k in ("t1", "t2", "t3"))
    assert script.beats[0].chart[0].extend == "right"
    assert json.dumps([a.model_dump() for a in script.beats[3].chart])


def test_pattern_scanners_report_states():
    cs = _series()
    tops = patterns.scan("double_top", cs)
    assert tops and all(h.extra["state"] in ("forming", "confirmed") for h in tops)
    assert all("neckline" in h.extra for h in tops)
    hs = patterns.scan("head_shoulders", cs)
    for h in hs:
        assert len(h.extra["points"]) == 5 and h.extra["labels"][2] == "H"
    assert patterns.scan("bollinger_squeeze", cs)
    assert patterns.scan("rsi_divergence", cs)
    assert patterns.scan("vwap_cross", cs)


def test_analysis_uses_the_chartist_tools_with_ids():
    steps = analyze(_series(), "XAU/USD")
    kinds = {s["action"] for s in steps}
    assert {"regression", "avwap", "vprofile", "keylevels", "session", "position", "study"} <= kinds, kinds
    ids = [s["id"] for s in steps if s.get("id")]
    assert len(ids) == len(set(ids)), "ids must be unique within one pass"
    pos = next(s for s in steps if s["action"] == "position")
    assert pos["state"] == "forming" and "example" in pos["label"]
    assert all(s["action"] != "pattern" or s["state"] in ("forming", "confirmed") for s in steps)
    # every time-bearing field is ISO (the director converts once)
    for s in steps:
        for k in ("time", "start", "end", "t1", "t2", "t3", "anchor"):
            if k in s:
                assert "T" in s[k], (s["action"], k)


def test_doctrine_and_curriculum_cover_the_tools():
    doc = drawing_doctrine()
    for tool in ("`channel`", "`regression`", "`pitchfork`", "`fib_ext`", "`position`", "`vprofile`", "`avwap`", "`study`", "`pattern`", "`alert`", "`keylevels`", "`remove`"):
        assert tool in doc, tool
    assert "forming" in doc and "invalidated" in doc
    cur = Curriculum()
    mod = cur.module("drawing_tools")
    assert mod and len(mod.lessons) >= 15
    scanners = {l.scanner for l in mod.lessons}
    assert {"double_top", "triangle", "head_shoulders", "rsi_divergence", "vwap_cross"} <= scanners
    for lesson in mod.lessons:
        assert lesson.scanner == "none" or lesson.scanner in patterns.SCANNERS, lesson.scanner
    assert cur.module("timeframes_practice")
    assert notes_for("Andrews pitchfork").plain.startswith("A pitchfork")
    assert "neckline" in notes_for("Head and shoulders").confirm
