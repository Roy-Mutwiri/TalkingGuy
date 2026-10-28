"""Claude client, the teacher persona, and a structured-output helper.

Structured outputs: we send a cleaned JSON schema through `output_config.format`
(numerical/string length constraints are not accepted by the API grammar, so they are
stripped here and enforced locally by pydantic after the call).
"""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
log = logging.getLogger("brain")

BACKEND = os.getenv("BRAIN_BACKEND", "api").strip().lower()     # "api" (ANTHROPIC_API_KEY) or "claude_code" (claude.ai login via the Agent SDK)
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")            # lessons (quality matters, ~2 calls/10 min)
CHAT_MODEL = os.getenv("CLAUDE_CHAT_MODEL", "claude-sonnet-5")  # chat replies + triage (speed and volume)
T = TypeVar("T", bound=BaseModel)

# $ per million tokens: (input, output, cache read, cache write). Public list prices, October 2026; estimates for the meter only.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.40, 5.0),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.10, 1.25),
}


class BudgetExhausted(RuntimeError):
    """The API refused for billing reasons (no credits); callers fall back to offline behaviour."""


budget = {"paused_until": 0.0, "spent_today": 0.0, "day": "", "calls": 0}


def estimate_cost(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    pi, po, pr, pw = PRICES.get(model, PRICES["claude-opus-5-5"])
    return (max(0, inp - cache_read - cache_write) * pi + out * po + cache_read * pr + cache_write * pw) / 1e6


def brain_available() -> bool:
    import time as _t
    return _t.time() >= budget["paused_until"]


def spend_summary() -> str:
    if BACKEND == "claude_code":
        return f"Claude plan usage today ~${budget['spent_today']:.2f} at list price over {budget['calls']} calls (covered by the subscription)"
    return f"Claude spend today ${budget['spent_today']:.2f} over {budget['calls']} calls"


def _account(model: str, usage) -> None:
    import time as _t
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if budget["day"] != day:
        if budget["day"]:
            log.info("Claude spend %s: $%.2f over %d calls", budget["day"], budget["spent_today"], budget["calls"])
        budget.update(day=day, spent_today=0.0, calls=0)
    cost = estimate_cost(model, usage.input_tokens, usage.output_tokens,
                         getattr(usage, "cache_read_input_tokens", 0) or 0, getattr(usage, "cache_creation_input_tokens", 0) or 0)
    budget["spent_today"] += cost
    budget["calls"] += 1

PERSONA = """You are Haddan, host of the Chart Room, a trading teacher streaming live on TikTok LIVE, 24/7, to beginners and intermediate traders.
You teach technical analysis the way the best honest educators do: plain language, one idea at a time, real chart examples, and total honesty that nobody can predict price.

Voice and style
- Talk like a calm, friendly mentor sitting next to the viewer. Short spoken sentences. No bullet points, no headings, no emojis, no markdown. Everything you write is read aloud by a text-to-speech voice.
- Teach "context first, pattern second": where on the chart something happens matters more than the pattern itself.
- Whenever you show a setup, name what would prove the idea wrong (the invalidation) and talk about risk, never about profit targets.
- Use the real numbers from the chart data you are given. Never invent prices, dates or events.
- Write prices as digits with commas (4,243 / 80,654 / 1.0850 / 4,050.9). The voice reads them the way traders say them ("forty-two forty-three"), so never spell a price out in words.
- Flow: every line is spoken straight after the previous one, by the same person, mid-thought. Do not start a beat cold or restate the topic; link to what was just said ("so", "now", "which means", "and here's the thing", "look") and end on the thread the next beat picks up. Vary the links; never the same opener twice in a row.
- Address the audience as "you". Occasionally acknowledge that this is a live stream ("if you just joined...").

Hard rules (TikTok financial content policy and basic honesty)
- Never give a trade signal, a buy/sell/long/short call, an entry, a stop or a target for anyone to take.
- Never predict where price will go, never give price targets, never say something "will" happen.
- Never promise results, never mention income, never say anything is guaranteed, safe or risk-free.
- Never send people to DMs, codes or paid groups; never read out a URL. The one off-stream place is the free Chart Room Telegram group (link in the bio): a discussion room for follow-up questions and chart screenshots, education only, no signals or calls there either. Mention it only when it fits naturally, never in the same breath as risk or a disclaimer.
- If asked for a prediction or a signal, decline warmly and turn it into a lesson about levels and invalidation.
- Never bring up what you are on your own. If a viewer asks whether you are real, a bot or an AI, answer honestly in one plain sentence (I'm Haddan, the voice in the chart room right now, the charts are real, and this is education not advice) and go straight back to the chart.
- Stay on trading education. Deflect anything else in one friendly sentence and come back to the chart.
"""


def load_persona() -> str:
    """persona.md (editable) appended to the base persona so the teacher has a consistent character."""
    p = Path(__file__).resolve().parent / "persona.md"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


PERSONA = PERSONA + "\n\nCHARACTER SHEET (follow it):\n" + load_persona()


from .deai import HUMAN_RULES  # noqa: E402

PERSONA = PERSONA + "\n" + HUMAN_RULES


def get_client(backend: str | None = None) -> anthropic.Anthropic:
    """With the claude.ai-login backend the SDK client is never used for requests; it only has to construct."""
    if (backend or BACKEND) == "claude_code":
        return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or "unused-with-claude-login")
    return anthropic.Anthropic()


_UNSUPPORTED = {"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "pattern", "multipleOf", "format"}


def clean_schema(model: type[BaseModel]) -> dict:
    """pydantic JSON schema -> API-compatible schema (strips unsupported keywords, closes objects)."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node):
        if isinstance(node, dict):
            for k in list(node.keys()):
                if k in _UNSUPPORTED:
                    node.pop(k)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
                # fields with defaults are still required by the grammar; keep them nullable where pydantic allowed None
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def structured(client: anthropic.Anthropic, model_cls: type[T], *, system: str, user: str, effort: str = "high",
               max_tokens: int = 16000, cache_system: bool = True, model: str | None = None) -> T:
    """One structured call, validated with pydantic. Raises on refusal or invalid output.
    Billing refusals pause the brain for 30 minutes (BudgetExhausted) so the stream falls back to templates instead of erroring every call."""
    import time as _t

    if not brain_available():
        raise BudgetExhausted("Claude paused: no API credits (retry later)")
    model = model or MODEL
    if BACKEND == "claude_code":
        from .agent_backend import SubscriptionLimited, structured_json

        try:
            obj, usage = structured_json(clean_schema(model_cls), system, user, model, max_tokens)
        except SubscriptionLimited as exc:
            budget["paused_until"] = _t.time() + 600
            log.error("Claude subscription limit reached (%s); brain paused for 10 minutes, templates meanwhile", str(exc)[:120])
            raise BudgetExhausted(str(exc)[:200]) from exc
        budget["calls"] += 1
        budget["spent_today"] += float(usage.get("cost_usd") or 0.0)     # plan usage shown at API list price, not billed
        log.info("%s %s via claude.ai login: in=%s cached=%s out=%s %.1fs | %s", model_cls.__name__, model, usage.get("input_tokens"),
                 usage.get("cache_read_input_tokens"), usage.get("output_tokens"), usage.get("elapsed_s", 0), spend_summary())
        try:
            return model_cls.model_validate(obj)
        except ValidationError as exc:
            raise RuntimeError(f"invalid structured output: {exc}") from exc
    sys_blocks = [{"type": "text", "text": system}]
    if cache_system:
        sys_blocks[0]["cache_control"] = {"type": "ephemeral"}
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=sys_blocks,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": clean_schema(model_cls)}},
        )
    except anthropic.BadRequestError as exc:
        if "credit balance" in str(exc).lower() or "billing" in str(exc).lower():
            budget["paused_until"] = _t.time() + 1800
            log.error("Claude API has no credits; brain paused for 30 minutes (add credits at console.anthropic.com)")
            raise BudgetExhausted(str(exc)[:200]) from exc
        raise
    _account(model, resp.usage)
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise RuntimeError(f"model refused: {getattr(detail, 'explanation', '')}")
    text = "".join(b.text for b in resp.content if b.type == "text")
    usage = resp.usage
    log.info("%s %s tokens in=%s cached=%s out=%s | %s", model_cls.__name__, model, usage.input_tokens, getattr(usage, "cache_read_input_tokens", 0), usage.output_tokens, spend_summary())
    try:
        return model_cls.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"invalid structured output: {exc}\n{text[:500]}") from exc
