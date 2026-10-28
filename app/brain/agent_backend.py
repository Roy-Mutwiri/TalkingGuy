"""Brain backend that runs through Claude Code's harness (Claude Agent SDK) using the claude.ai login
on this machine, instead of an API key.

Enable with BRAIN_BACKEND=claude_code in .env. The SDK spawns the `claude` CLI for each call with no
tools, one turn, and a JSON schema for the output, so it behaves like a plain structured-output call.

Read before relying on it: Anthropic's Agent SDK docs say products built on the SDK must use API keys
and that claude.ai logins are not offered for third-party products unless approved. This backend only
uses the owner's own login on the owner's own machine, never a shared or resold one, and it falls back
to the offline teacher whenever the subscription's usage window is exhausted.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

log = logging.getLogger("brain")

MODEL_ALIAS = {"claude-opus-5-5": "opus", "claude-opus-5": "opus", "claude-sonnet-5": "sonnet", "claude-sonnet-5-5": "sonnet",
               "claude-haiku-4-5-20251001": "haiku", "claude-fable-5-1": "fable"}


class SubscriptionLimited(RuntimeError):
    """The subscription's usage window is exhausted (or the CLI is not logged in)."""


def _limited(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("hit your session limit", "hit your weekly limit", "usage limit", "rate limit", "429", "not logged in", "please run /login", "authentication"))


def _strict_schema(node, compact: bool = True):
    """The CLI validates the schema in strict mode: drop keywords it does not know (pydantic's `discriminator`).
    The schema travels on the CLI command line, which Windows caps at 32 KB, so `compact` also drops the
    prose keywords (description, title, examples); the field guidance lives in the prompt instead."""
    drop = {"discriminator"} | ({"description", "title", "examples"} if compact else set())
    if isinstance(node, dict):
        return {k: _strict_schema(v, compact) for k, v in node.items() if k not in drop}
    if isinstance(node, list):
        return [_strict_schema(v, compact) for v in node]
    return node


# Windows passes --system-prompt and --json-schema as command-line arguments (32,767 chars in total); the user
# message goes through stdin and has no such limit. Keep the command line small by moving the long part of the
# system prompt into the message when needed.
CMDLINE_BUDGET = 20000


def _package(system: str, user: str, schema_json: str) -> tuple[str, str]:
    if len(system) + len(schema_json) <= CMDLINE_BUDGET:
        return system, user
    head, _, tail = system.partition("\n")
    if len(head) > 2000:
        head, tail = system[:1500], system[1500:]
    moved = ("OPERATING INSTRUCTIONS (these are your standing instructions; follow them as the system prompt):\n" + tail.strip() +
             "\n\n--- REQUEST ---\n" + user)
    return head.strip() or "You are the host described below.", moved


async def _run(schema: dict, system: str, user: str, model: str, max_tokens: int) -> tuple[dict, dict]:
    from claude_agent_sdk import ClaudeAgentOptions, query

    schema = _strict_schema(schema)
    system, user = _package(system, user, json.dumps(schema))

    env = {k: v for k, v in os.environ.items()}
    env.pop("ANTHROPIC_API_KEY", None)           # the login, not a (possibly empty) API key, must authenticate this process
    opts = ClaudeAgentOptions(
        system_prompt=system, allowed_tools=[], max_turns=1, model=MODEL_ALIAS.get(model, model),
        output_format={"type": "json_schema", "schema": schema}, env=env, cwd=os.getcwd(),
    )
    texts: list[str] = []
    structured = None
    usage: dict = {}
    async for msg in query(prompt=user, options=opts):
        name = type(msg).__name__
        if name == "AssistantMessage":
            for b in getattr(msg, "content", []):
                if hasattr(b, "text"):
                    texts.append(b.text)
        elif name == "ResultMessage":
            sub = getattr(msg, "subtype", "")
            usage = dict(getattr(msg, "usage", None) or {})
            usage["cost_usd"] = getattr(msg, "total_cost_usd", None)
            structured = getattr(msg, "structured_output", None)
            res = str(getattr(msg, "result", "") or "")
            if sub != "success":
                if _limited(res) or _limited(sub):
                    raise SubscriptionLimited(res[:200] or sub)
                raise RuntimeError(f"agent result {sub}: {res[:200]}")
            if not texts and res:
                texts.append(res)
    if structured is None:
        raw = "".join(texts).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        structured = json.loads(raw)
    return structured, usage


def structured_json(schema: dict, system: str, user: str, model: str, max_tokens: int = 16000) -> tuple[dict, dict]:
    """Synchronous entry (callers run this inside asyncio.to_thread). Returns (json_object, usage)."""
    t0 = time.time()
    try:
        obj, usage = asyncio.run(_run(schema, system, user, model, max_tokens))
    except SubscriptionLimited:
        raise
    except Exception as exc:  # noqa: BLE001
        if _limited(str(exc)):
            raise SubscriptionLimited(str(exc)[:200]) from exc
        raise
    usage["elapsed_s"] = round(time.time() - t0, 1)
    return obj, usage
