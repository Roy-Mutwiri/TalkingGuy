from app.chat.moderation import Moderator
from app.chat.tiktok_reader import ChatReader
from app.chat.triage import Triager


def test_moderator_keeps_trading_questions():
    m = Moderator()
    q = m.assess("sam", "what is a doji candle and how do you trade it?")
    assert q is not None and q.user == "sam" and q.score >= 2


def test_moderator_drops_spam_profanity_and_low_value():
    m = Moderator()
    assert m.assess("x", "hi") is None
    assert m.assess("x", "join my telegram t.me/pumps for signals") is None
    assert m.assess("x", "this is fucking great chart") is None
    assert m.assess("x", "lol") is None


def test_moderator_dedupes_and_cools_down():
    m = Moderator(per_user_cooldown_s=120)
    assert m.assess("a", "how do you find support levels?") is not None
    assert m.assess("b", "how do you find support levels?") is None  # duplicate text
    assert m.assess("a", "what is rsi used for?") is None  # same user within cooldown


def test_reader_pending_and_priority_heap():
    reader = ChatReader(unique_id="")
    reader.offer("u1", "why does volume matter on a breakout?")
    reader.offer("u2", "first!!!")
    reader.offer("u3", "is bitcoin going to 100k?")
    batch = reader.take_pending()
    assert [q.user for q in batch] == ["u1", "u3"]
    reader.push(batch[0], "medium")
    reader.push(batch[1], "high")
    reader.push(batch[0], "spam")          # ignored
    best = reader.pop(max_rank=0)
    assert best is not None and best.q.user == "u3"
    assert reader.pop(max_rank=0) is None  # only medium left
    assert reader.pop(max_rank=1).q.user == "u1"


def test_triage_heuristic_priorities_and_topics():
    t = Triager(client=None)
    items = t.heuristic([
        "can you explain fibonacci retracement please?",
        "hey theo good evening from Nairobi",
        "W",
        "how do I size a position with a 1% risk",
    ])
    assert items[0].priority == "high" and "fibonacci" in (items[0].topic or "")
    assert items[1].priority == "medium"
    assert items[2].priority == "low"
    assert items[3].priority == "high" and items[3].topic
