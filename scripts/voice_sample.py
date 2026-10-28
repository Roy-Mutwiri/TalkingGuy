"""Render Theo's mood map to WAV files so you can hear what each delivery label does.

    python scripts/voice_sample.py            # writes data_cache/voice_samples/<mood>.wav

Each file is the same four lines spoken in one mood through the Edge voice with the same
humanizing chain the stream uses. Listen with any player; nothing is sent to the stream.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LINES = {
    "cheerful": "Okay, this is the interesting part. Which detail would you check first?",
    "excited": "Sam, you spotted it, the second attempt! Let's look at why that matters.",
    "teach": "I promised you the losing version. Here it is. Watch what changes when we remove that confirmation.",
    "considerate": "No rush, Nia. Let's make this easier with one example.",
    "curious": "Wick or close, which one confirms it? Type W or C.",
    "warm": "Welcome in, perfect timing. We're on support and resistance.",
    "show": "Okay chat, here we go! Gold just tapped the level again. Type H if you think it holds, N if not. Let's go!",
}
# Energetic Edge voices worth auditioning for the show (switch in the console voice selector)
VOICES = ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-GuyNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural", "en-AU-WilliamNeural"]


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    from app.voice.edge_voice import EdgeSpeaker

    out = Path("data_cache/voice_samples")
    out.mkdir(parents=True, exist_ok=True)
    sp = EdgeSpeaker(voice=os.getenv("TTS_VOICE", "en-US-AndrewMultilingualNeural"))
    for mood, line in LINES.items():
        sp.mood = mood
        rate, pitch = sp.prosody(line)
        audio = await sp._fetch(line)
        sf.write(out / f"{mood}.wav", audio.astype(np.float32), 24000)
        print(f"{mood:12} rate {rate:>5} pitch {pitch:>5}  -> {out / (mood + '.wav')}")
    if "--voices" in sys.argv:            # same show line, several voices: pick the one with the most life
        line = LINES["show"]
        for v in VOICES:
            try:
                vs = EdgeSpeaker(voice=v)
                vs.mood = "show"
                audio = await vs._fetch(line)
                sf.write(out / f"voice_{v}.wav", audio.astype(np.float32), 24000)
                print(f"voice {v:34} -> {out / ('voice_' + v + '.wav')}")
            except Exception as exc:  # noqa: BLE001
                print(f"voice {v:34} failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
