from app.chat.names import speakable_name, strip_for_speech
from app.voice.pronounce import humanize


def test_emojis_and_decoration_never_reach_speech():
    out = humanize("Gold is flying 🚀🚀 to the moon 😂 #gold **strong** @maria said ✅ done")
    assert "🚀" not in out and "😂" not in out and "✅" not in out
    assert "#" not in out and "*" not in out and "@" not in out
    assert "maria" in out and "strong" in out
    assert strip_for_speech("🔥Ali Gold🔥").strip() == "Ali Gold"


def test_speakable_names_from_handles():
    assert speakable_name("maria_fx_2024") == "Maria"
    assert speakable_name("kev99") == "Kev"
    assert speakable_name("🔥Ali Gold🔥") == "Ali"
    assert speakable_name("user8812937", fallback="friend") == "friend"
    assert speakable_name("") == "friend"
    assert speakable_name("AhmedTrades") == "Ahmed"
