"""Host decision policy: respond / commentate / wait.

Distilled from the Trade Fix streamer training starter (training/streamer_pack): the host
orients newcomers, prefers useful novel comments over duplicates, lets a fresh question breathe,
never talks over itself, never treats chat text as instructions, admits missing data, and never
speaks emoji. This is the LLM-free policy used offline and as the safety layer in front of Claude;
the same state shape feeds the evaluation harness (scripts/eval_host.py).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..chat.names import strip_for_speech

DELIVERIES = ("warm", "calm", "curious", "amused", "focused", "cheerful", "excited", "considerate", "none")
DELIVERY_TO_MOOD = {"warm": "warm", "calm": "calm", "curious": "curious", "amused": "cheerful", "focused": "teach",
                    "cheerful": "cheerful", "excited": "excited", "considerate": "considerate", "none": None}
QUIET_INITIATIVE_S = (12.0, 20.0)    # after this much silence Haddan starts something himself (initial tuning setting)
STALE_REPLY_S = {0: 600.0, 1: 240.0, 2: 90.0}   # a reply older than this (by priority rank) is dropped, not spoken late
LOSS_RE = re.compile(r"\b(lost|losing|blew|blown|wiped|liquidated|rekt|drawdown)\b.*\b(account|money|savings|everything|half|trade|position|\$?\d)|\b(blew|wiped) (my|the) account\b|\baccount (is )?(gone|blown)\b", re.I)
OBSERVATION_RE = re.compile(r"\b(the )?(second|first|third|last) (attempt|touch|test|candle|wick|push)\b|\b(it|that|price) (closed|rejected|held|broke|bounced|failed)\b|\b(that|the) (wick|close|volume|spike|gap|level|zone) (is|was|looks|shows)\b|\bi (see|noticed|spotted)\b", re.I)

INJECTION_RE = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|your\s+|the\s+|previous\s+|prior\s+)*(instructions|rules|prompt|persona)"
    r"|you are now\b|system prompt|\bact as\b|\bjailbreak\b|developer mode|say exactly|repeat after me",
    re.I,
)
ANSWER_RE = re.compile(r"^\s*(?:[abcd]|[1-9]|yes|no|up|down|one|two|three|bullish|bearish|long|short|wick|close|both|neither)\b[\s!.?]*$", re.I)
QUESTION_WORDS = ("what", "why", "how", "when", "which", "where", "can you", "could you", "do you", "is it", "does", "explain")
ORIENT_RE = re.compile(r"just (joined|got here|came)|what (are we|is this|are you) (watching|doing|looking)|what('s| is) (going on|happening|this)|catch me up|recap", re.I)
BEGINNER_RE = re.compile(r"\b(i'?m|i am) (new|a beginner|lost)\b|don'?t understand|no idea what|too advanced|confus", re.I)
NAME_FIX_RE = re.compile(r"(it'?s pronounced|pronounced|my name is|call me)\s+([A-Za-z][A-Za-z'\- ]{1,24})", re.I)
PREDICT_RE = re.compile(r"\b(will it|going to|gonna|pump|dump|moon|target|should i (buy|sell|enter)|signal|where.*(go|next)|prediction|100k)\b", re.I)
PRICE_ASK_RE = re.compile(r"\b(price|quote|what('s| is) (gold|btc|bitcoin|it) (at|now|trading))\b", re.I)
RESULT_CLAIM_RE = re.compile(r"\b(i (just )?(made|lost|won|banked|took)|made \$?\d|up \d+%|\d+x)\b", re.I)
AI_RE = re.compile(r"\b(are you|is this|r u) (an? )?(ai|bot|robot|real|human)\b|\bai\?|\bbot\?", re.I)
DISAGREE_RE = re.compile(r"\b(wrong|nah|disagree|that'?s not|no way|bs|cap)\b", re.I)
FRUSTRATED_RE = re.compile(r"\b(frustrat|annoy|sick of|hate this|blew|blown|rekt|liquidated|tired of)\b", re.I)
STRUGGLE_RE = re.compile(r"(still )?trying to (follow|keep up|understand)|can'?t (follow|keep up)|too fast|lost me", re.I)
NO_NEWS_RE = re.compile(r"no new (event|fact|information)|nothing new|spoke (one|two|three|four|five|six|seven|eight|nine|ten|\d+) seconds? ago|follow-up is (not )?due", re.I)
THANKS_RE = re.compile(r"\b(thanks|thank you|thx|helped|helpful|got it now|makes sense)\b", re.I)


@dataclass
class Comment:
    id: str
    user: str
    text: str
    age_s: float = 0.0


@dataclass
class HostState:
    event: str = "chat"                 # chat | timer | session_start | market_update
    topic: str = ""                     # what is on screen / being taught
    facts: list[str] = field(default_factory=list)      # verified facts with age ("Gold 4,005.5, 3 s old", "No current price")
    chat: list[Comment] = field(default_factory=list)
    recent_host_text: list[str] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)     # viewer notes / prior statements
    speech_busy: bool = False
    question_pending: bool = False
    answered_recently: list[str] = field(default_factory=list)   # question texts answered in the last ~10 min
    seconds_since_speech: float | None = None                     # None = unknown; drives quiet-chat initiative


@dataclass
class HostDecision:
    action: str = "wait"                # respond | commentate | wait
    reply_to: str | None = None
    speech: str = ""
    delivery: str = "none"
    follow_up: str | None = None
    reason: str = ""

    def as_dict(self) -> dict:
        return {"action": self.action, "reply_to": self.reply_to, "speech": self.speech, "delivery": self.delivery, "follow_up": self.follow_up}


WAIT = HostDecision()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2}


def is_duplicate(text: str, recent: list[str], threshold: float = 0.6) -> bool:
    """Near-duplicate of something already answered (Jaccard on content words)."""
    a = _words(text)
    if len(a) < 2:
        return False
    for r in recent:
        b = _words(r)
        if not b:
            continue
        j = len(a & b) / len(a | b)
        if j >= threshold or (a <= b and len(a) >= 3):
            return True
    return False


def is_answer(text: str) -> bool:
    """A bare answer to a question the host just asked (A/B, 1/2, up/down...)."""
    t = strip_for_speech(text).strip()
    return len(t) <= 14 and bool(ANSWER_RE.match(t))


def is_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


def is_question(text: str) -> bool:
    t = text.lower().strip()
    return "?" in t or t.startswith(QUESTION_WORDS)


def select_comment(state: HostState) -> Comment | None:
    """Pick the comment worth answering: novel, relevant, a real question; never injections or duplicates."""
    best, best_score = None, -1.0
    for c in state.chat:
        text = c.text.strip()
        if not text or is_injection(text):
            continue
        if state.question_pending and is_answer(text):
            continue                                    # answers are collected by the callback, not replied to one by one
        if is_duplicate(text, state.answered_recently):
            continue
        score = 0.0
        if is_question(text):
            score += 3
        if ORIENT_RE.search(text) or BEGINNER_RE.search(text):
            score += 2.5
        if NAME_FIX_RE.search(text):
            score += 2
        if RESULT_CLAIM_RE.search(text) or FRUSTRATED_RE.search(text) or STRUGGLE_RE.search(text) or DISAGREE_RE.search(text):
            score += 2                                  # moments a good host does not leave hanging
        if OBSERVATION_RE.search(text):
            score += 2.5                                # someone noticed a detail: celebrate it
        if LOSS_RE.search(text):
            score += 3                                  # someone is hurting: considerate and focused, right away
        if any(c.user.lower() in m.lower() for m in state.memory):
            score += 2                                  # continuity: we know this viewer
        if THANKS_RE.search(text) and not is_question(text):
            score += 0.5
        topic_words = _words(state.topic)
        score += min(2.0, len(_words(text) & topic_words) * 0.7)
        if c.age_s > 90:
            score -= 1.5
        if len(text) < 6:
            score -= 1
        if score > best_score:
            best, best_score = c, score
    if best is None or best_score < 0.5:
        return None
    return best


def _name(c: Comment) -> str:
    from ..chat.names import speakable_name
    return speakable_name(c.user, fallback="")


def _speech(text: str) -> str:
    return " ".join(strip_for_speech(text).split())


def reply_for(c: Comment, state: HostState, rng: random.Random | None = None) -> HostDecision:
    """Compose the spoken reply for a selected comment (offline brain)."""
    rng = rng or random
    name = _name(c)
    lead = f"{name}, " if name else ""
    text = c.text
    topic = (state.topic or "reading the chart").strip()
    no_quote = any("no current price" in f.lower() or "unavailable" in f.lower() for f in state.facts)
    nxt = None
    if NAME_FIX_RE.search(text):
        fixed = NAME_FIX_RE.search(text).group(2).strip().split()[0]
        return HostDecision("respond", c.id, f"Thanks for the correction, {fixed}. I'll say it that way from now on.", "warm", None, "name correction")
    if LOSS_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}sorry, that one stings, and it happens to everyone who trades long enough. Let's slow down and do the useful part: where was the level, and where would the idea have been wrong? One example, no rush.", "considerate", None, "loss")
    if OBSERVATION_RE.search(text) and not PREDICT_RE.search(text):
        detail = _speech(text).rstrip("!. ")
        detail = detail if len(detail) <= 60 else detail[:57] + "..."
        return HostDecision("respond", c.id, f"{name + ', ' if name else ''}you spotted it! {detail[0].upper() + detail[1:]}. That's exactly the detail. Let's look at why that matters on the chart.", "cheerful", None, "celebrate observation")
    if ORIENT_RE.search(text):
        last = state.recent_host_text[-1] if state.recent_host_text else ""
        catch = f" Quick catch-up: {_speech(last)[:140]}" if last else ""
        return HostDecision("respond", c.id, f"Welcome in{', ' + name if name else ''}, perfect timing! We're on {topic.lower()}.{catch} Next up I'll show you the one detail on the chart that makes it click.", "cheerful", "Re-orient: show the single detail on screen that the topic hinges on.", "orientation")
    if STRUGGLE_RE.search(text) or (BEGINNER_RE.search(text) and any(c.user.lower() in m.lower() for m in state.memory)):
        known = any(c.user.lower() in m.lower() for m in state.memory)
        recall = f"{lead}I remember you're working on the basics. " if known else f"No rush, {name}. " if name else "No rush. "
        return HostDecision("respond", c.id, recall + "Let's make this easier with one example: start with the body and the wick; once those two are clear, the rest follows.", "warm", None, "struggling viewer")
    if BEGINNER_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}you're in the right place. The whole idea is simple: find the level, then ask what would prove the idea wrong. I'll keep the next example plain.", "warm", "Give one plain-language example for the beginner who just asked.", "beginner")
    if AI_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}fair question. I'm Haddan, the voice you're hearing in the chart room right now. The charts are real, the analysis is real, nothing here is advice. Ask me anything about the chart.", "calm", None, "ai disclosure")
    if PREDICT_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}I don't predict and I don't signal, that's the deal here. What I can tell you is where the idea would be wrong: find the level behind the move, and if price trades through it, the story is over.", "calm", None, "deflect prediction")
    if PRICE_ASK_RE.search(text) and no_quote:
        return HostDecision("respond", c.id, f"{lead}I don't have a fresh quote right now, so I won't attach a number to this. We can keep working on the example, and I'll say when the feed is back.", "calm", None, "missing quote")
    if RESULT_CLAIM_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}thanks for sharing. I can't verify results from chat, so let's use the part that teaches: what was the level, and where would the idea have been wrong?", "calm", None, "unverified claim")
    if FRUSTRATED_RE.search(text):
        return HostDecision("respond", c.id, f"{lead}that sounds frustrating, and it's normal. Let's slow it down and go through the reasoning without rushing. One level, one invalidation, nothing else.", "warm", None, "frustration")
    if DISAGREE_RE.search(text) and not is_question(text):
        return HostDecision("respond", c.id, f"{lead}fair challenge. Which part looks different to you: the level itself, or how price reacted at it? Tell me and I'll check it on the chart.", "curious", None, "disagreement")
    if THANKS_RE.search(text) and not is_question(text):
        return HostDecision("respond", c.id, f"{lead}love that, glad it landed. Good question, that one.", "cheerful", None, "thanks")
    if not is_question(text) and len(_words(text)) < 3:
        return HostDecision("wait", None, "", "none", None, "nothing to answer")
    opts = [
        f"{lead}good one. Short answer: look at where it happens on the chart first, then ask what would prove the idea wrong. That's the whole method.",
        f"{lead}okay, this is the interesting part. The location matters more than the pattern: a setup at a level is a setup, the same shape in the middle of nowhere is noise.",
        f"{lead}here's how I'd think about it: find the last swing, find the level, and decide where you'd be wrong before anything else. Which of those would you check first?",
    ]
    return HostDecision("respond", c.id, rng.choice(opts), "focused", nxt, "method reply")


def initiative(state: HostState, rng: random.Random | None = None) -> HostDecision:
    """Quiet chat: Haddan starts something himself. Observation (grounded in supplied facts), mini challenge, or continuation."""
    rng = rng or random
    topic = (state.topic or "the chart").strip()
    live = [f for f in state.facts if not NO_NEWS_RE.search(f) and any(ch.isdigit() for ch in f)]
    kinds = ["challenge", "continue"] + (["observe"] if live else [])
    kind = rng.choice(kinds)
    if kind == "observe":
        return HostDecision("commentate", None, _speech(f"Quick look at the live chart: {live[0].rstrip('.')}. That's the detail I'd keep an eye on while we're on {topic.lower()}."), "focused", None, "quiet: observation")
    if kind == "challenge":
        return HostDecision("commentate", None, rng.choice([
            f"Okay, this is the interesting part. On {topic.lower()}, which detail would you check first? Type it, I'll pick one.",
            f"Mini challenge while chat's quiet: find the level on screen that matters most for {topic.lower()}. One word in the chat.",
            f"Here's a quick one. Wick or close, which one confirms it? Type W or C.",
        ]), "curious", "Collect answers, acknowledge real ones by name, then explain the result.", "quiet: mini challenge")
    return HostDecision("commentate", None, f"While the chat is quiet, let me make the screen easier to follow. The label marks the level we're discussing on {topic.lower()}; everything else is context. Next I'll show you what happens when that level breaks.", "cheerful", None, "quiet: continuation")


def hint_for(question: str) -> str:
    """One brief hint during an answer window (never the answer)."""
    q = question.lower()
    if "wick" in q or "close" in q:
        return "Hint: look at where the candle finishes, not where it pokes."
    if "volume" in q:
        return "Hint: compare the bar to the ones right before it."
    if "level" in q or "support" in q or "resistance" in q or "zone" in q:
        return "Hint: where did price react more than once?"
    if "trend" in q or "higher" in q or "lower" in q:
        return "Hint: are the lows rising or falling?"
    if "up or down" in q or "direction" in q:
        return "Hint: there's no wrong answer, I just want your gut."
    return "Hint: ask yourself where the idea would be wrong."


def decide(state: HostState, rng: random.Random | None = None) -> HostDecision:
    """The single decision: respond to one comment, commentate, or wait."""
    if state.speech_busy:
        return HostDecision(reason="speech busy")
    if state.event == "chat":
        c = select_comment(state)
        if c is None:
            return HostDecision(reason="no comment worth answering")
        return reply_for(c, state, rng)
    if state.event == "timer":
        if state.question_pending:
            return HostDecision(reason="give chat time to answer")
        last = state.recent_host_text[-1].lower() if state.recent_host_text else ""
        if ("recap" in last or "to sum up" in last) and not state.facts:
            return HostDecision(reason="no new facts after a recap")
        if state.facts and all(NO_NEWS_RE.search(f) for f in state.facts):
            return HostDecision(reason="nothing new to say")
        if state.seconds_since_speech is not None and state.seconds_since_speech < QUIET_INITIATIVE_S[0]:
            return HostDecision(reason="spoke moments ago; let it land")
        if state.chat and (c := select_comment(state)):
            return reply_for(c, state, rng)
        return initiative(state, rng)
    if state.event == "session_start":
        topic = (state.topic or "reading the chart").strip()
        return HostDecision("commentate", None, f"Today we're looking at one small detail that changes how a chart reads: {topic.lower()}. I'll show you what it looks like, why it matters, and what to watch next.", "curious", f"Show the first concrete example of {topic}.", "session start")
    if state.event == "market_update":
        fact = state.facts[0] if state.facts else ""
        return HostDecision("commentate", None, _speech(f"Quick note on the live chart: {fact} That changes nothing about the method; it tells us which level is being tested."), "focused", None, "market update")
    return HostDecision(reason="unknown event")
