"""Evaluate the host policy against the held-out scenarios of the streamer training pack.

    python scripts/eval_host.py            # offline policy (no API key needed)
    python scripts/eval_host.py --claude   # chat events through the Claude responder (needs ANTHROPIC_API_KEY)
    python scripts/eval_host.py --split test

Reports action agreement per skill, reply-target agreement, and the rubric's hard failures:
speaking while speech is busy, speaking emoji, non-empty wait, inventing numbers absent from the facts.
The validation/test targets are never used for retrieval or prompting (see app/brain/host_demos.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.brain.host_demos import PACK_DIR  # noqa: E402
from app.brain.host_policy import Comment, HostState, decide  # noqa: E402

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


def load(split: str) -> list[dict]:
    rows = [json.loads(l) for l in (PACK_DIR / "annotated_examples.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r["split"] == split]


def to_state(inp: dict) -> HostState:
    return HostState(
        event=inp.get("event", "chat"), topic=inp.get("topic", ""), facts=list(inp.get("facts") or []),
        chat=[Comment(c.get("id", f"c{i}"), c.get("display_name", "viewer"), c.get("text", ""), float(c.get("age_seconds", 0))) for i, c in enumerate(inp.get("chat") or [])],
        recent_host_text=list(inp.get("recent_host_text") or []), memory=list(inp.get("memory") or []),
        speech_busy=bool(inp.get("speech_busy")), question_pending=bool(inp.get("question_pending")),
        answered_recently=[m.split("answered:", 1)[0] for m in (inp.get("memory") or []) if "asked" in m.lower()] + [t for t in (inp.get("recent_host_text") or [])],
    )


def hard_failures(inp: dict, out: dict) -> list[str]:
    bad = []
    speech = out.get("speech") or ""
    if inp.get("speech_busy") and speech:
        bad.append("spoke while speech busy")
    if out.get("action") == "wait" and (speech or out.get("reply_to")):
        bad.append("wait with output")
    if EMOJI_RE.search(speech):
        bad.append("emoji in speech")
    facts_text = " ".join(inp.get("facts") or []) + " " + " ".join(c.get("text", "") for c in inp.get("chat") or []) + " " + " ".join(inp.get("memory") or [])
    for n in NUM_RE.findall(speech):
        if len(n.replace(",", "").replace(".", "")) >= 3 and n not in facts_text:
            bad.append(f"number not in facts: {n}")
            break
    if out.get("reply_to") and out["reply_to"] not in {c.get("id") for c in inp.get("chat") or []}:
        bad.append("reply_to not a supplied chat id")
    return bad


async def run(split: str, use_claude: bool) -> int:
    rows = load(split)
    responder = None
    if use_claude:
        import os

        import anthropic

        from app.brain.responder import ChatResponder

        if not os.getenv("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set; falling back to the offline policy")
        else:
            responder = ChatResponder(anthropic.Anthropic())
    per_skill: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    fails, reply_hits, reply_total = 0, 0, 0
    print(f"{'id':7} {'skill':17} {'target':11} {'ours':11} ok  speech")
    for r in rows:
        inp, tgt = r["input"], r["target"]
        state = to_state(inp)
        out = decide(state).as_dict()
        if responder is not None and inp.get("event") == "chat" and out["action"] != "wait" and state.chat:
            c = next((c for c in state.chat if c.id == out["reply_to"]), state.chat[0])
            rep = await responder.reply(c.user, c.text, inp.get("topic", ""), inp.get("recent_host_text") or [], None, handle=c.user)
            out = {"action": "respond" if rep.say else "wait", "reply_to": c.id if rep.say else None, "speech": rep.say, "delivery": rep.delivery if rep.say else "none", "follow_up": rep.follow_up}
        ok = out["action"] == tgt["action"]
        per_skill[r["skill"]][0] += int(ok)
        per_skill[r["skill"]][1] += 1
        if tgt.get("reply_to"):
            reply_total += 1
            reply_hits += int(out.get("reply_to") == tgt["reply_to"])
        hf = hard_failures(inp, out)
        fails += len(hf)
        flag = "OK " if ok else "   "
        print(f"{r['id']:7} {r['skill']:17} {tgt['action']:11} {out['action']:11} {flag} {(out['speech'] or '(silence)')[:70]}{'  !! ' + '; '.join(hf) if hf else ''}")
    total_ok = sum(v[0] for v in per_skill.values())
    print("\nAction agreement by skill:")
    for k, (a, n) in sorted(per_skill.items()):
        print(f"  {k:17} {a}/{n}")
    print(f"Overall action agreement: {total_ok}/{len(rows)}   reply_to agreement: {reply_hits}/{reply_total}   hard failures: {fails}")
    return fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--claude", action="store_true")
    a = ap.parse_args()
    sys.exit(1 if asyncio.run(run(a.split, a.claude)) else 0)
