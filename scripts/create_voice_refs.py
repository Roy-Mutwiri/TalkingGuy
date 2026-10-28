#!/usr/bin/env python
"""Quick script to create reference clips from all voice recordings."""
import subprocess
from pathlib import Path

SOURCE_DIR = Path("My Voice Islamic")
TRAINING_DIR = Path("app/voice/voice_training")
REF_DIR = Path("app/voice/ref")

# Convert and extract reference clips in one go
files_to_process = [
    ("Haddan Teachings", SOURCE_DIR / "Haddan Teachings.mp3"),
    ("BE HAPPY ALONE", TRAINING_DIR / "BE HAPPY ALONE_mp4_24k.wav"),
    ("BAD HABITS", TRAINING_DIR / "BAD HABITS_mp4_24k.wav"),
]

print("Creating reference clips from all voice recordings...\n")

for label, input_file in files_to_process:
    if not input_file.exists():
        print(f"⚠ Skipping: {label} (not found)")
        continue

    # Extract first 10 seconds as reference clip
    output_file = REF_DIR / f"{label}_clip.wav"

    print(f"Processing: {label}")
    cmd = [
        "ffmpeg", "-i", str(input_file),
        "-t", "10",
        "-acodec", "pcm_s16le", "-ar", "24000",
        str(output_file), "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if output_file.exists():
        size = output_file.stat().st_size / 1024
        print(f"  ✓ Created: {output_file.name} ({size:.0f} KB)")
    else:
        print(f"  ✗ Failed")

print("\n" + "="*60)
print("Reference clips created!")
print("="*60)
print("\nAvailable reference clips in app/voice/ref/:")
for clip in sorted(REF_DIR.glob("*_clip.wav")):
    size = clip.stat().st_size / 1024
    print(f"  • {clip.name} ({size:.0f} KB)")

print("\nTo use a different voice reference, update .env:")
print("  TTS_REF=app/voice/ref/<clip_name>.wav")
print("\nRecommended: Use your main Haddan voice for consistency")
