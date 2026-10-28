"""Generate ORIGINAL background beats locally with Meta's MusicGen (runs on the RTX GPU).
The output is yours: no label, no publisher, nothing for TikTok's copyright matching to hit.

    .venv\\Scripts\\python scripts\\make_music.py --count 6 --seconds 30
    (first run downloads facebook/musicgen-small, ~2.3 GB)

Tracks land in music/ and the stream picks them up on the next start. Styles are tuned to
"viral-feeling" instrumental loops: afrobeats, amapiano, latin pop, lo-fi hip hop, phonk,
melodic trap, reggaeton. Edit PROMPTS to taste.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

PROMPTS = [
    "upbeat afrobeats instrumental, catchy marimba hook, log drums, 110 bpm, radio-ready, no vocals",
    "amapiano instrumental with deep log drum bassline, shakers, piano stabs, 112 bpm, club energy, no vocals",
    "latin pop reggaeton instrumental, dembow rhythm, bright synth hook, 95 bpm, summer party, no vocals",
    "melodic trap instrumental, 808 bass, catchy flute melody, 140 bpm, hype, no vocals",
    "chill lo-fi hip hop beat, warm vinyl, mellow piano, 85 bpm, study vibe, no vocals",
    "phonk drift instrumental, cowbell, distorted 808, aggressive, 130 bpm, no vocals",
    "dance pop instrumental, four on the floor, euphoric synth chords, 124 bpm, festival, no vocals",
    "funky house instrumental, filtered disco samples, groovy bass, 122 bpm, no vocals",
    "arabic pop instrumental, oud melody, darbuka and riq percussion, string section, 100 bpm, festive, no vocals",
    "khaleeji pop instrumental, Gulf rhythm, oud and qanun, synth bass, 96 bpm, modern, no vocals",
    "arabic trap instrumental, maqam melody on ney flute, heavy 808, 90 bpm, dark and catchy, no vocals",
    "egyptian shaabi mahraganat instrumental, electro beat, keyboard hooks, 110 bpm, street party, no vocals",
    "middle eastern dance instrumental, dabke rhythm, mijwiz-style synth lead, 120 bpm, wedding energy, no vocals",
]
ARABIC = [p for p in PROMPTS if any(k in p for k in ("arabic", "khaleeji", "egyptian", "middle eastern"))]


def main(count: int, seconds: int, model_name: str, style: str = "mix") -> None:
    import torch
    import soundfile as sf
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    out_dir = Path("music"); out_dir.mkdir(exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("loading", model_name, "on", device)
    processor = AutoProcessor.from_pretrained(model_name)
    model = MusicgenForConditionalGeneration.from_pretrained(model_name).to(device)
    sr = model.config.audio_encoder.sampling_rate
    tokens = int(seconds * 50)  # ~50 tokens per second
    pool = ARABIC if style == "arabic" else PROMPTS
    prompts = random.sample(pool, k=min(count, len(pool))) + [random.choice(pool) for _ in range(max(0, count - len(pool)))]
    for i, prompt in enumerate(prompts, 1):
        inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
        with torch.no_grad():
            audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=tokens)
        wav = audio[0, 0].cpu().numpy()
        name = out_dir / f"beat_{i:02d}_{prompt.split(',')[0].replace(' ', '_')[:28]}.wav"
        sf.write(name, wav, sr)
        print(f"[{i}/{len(prompts)}] {name} ({len(wav) / sr:.0f}s)")
    print("done. Restart the stream to pick up the new tracks.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument("--seconds", type=int, default=30, help="MusicGen caps around 30 s per clip; the bed loops tracks")
    ap.add_argument("--model", default="facebook/musicgen-small")
    ap.add_argument("--style", default="mix", choices=["mix", "arabic"], help="arabic = only Middle Eastern styles")
    a = ap.parse_args()
    sys.exit(main(a.count, a.seconds, a.model, a.style))
