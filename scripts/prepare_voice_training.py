#!/usr/bin/env python
"""Prepare all voice recordings for Chatterbox voice training.

Converts all audio to 24kHz WAV, analyzes characteristics, and creates
multiple reference clips from different parts of the recordings.
"""
import subprocess
import json
from pathlib import Path
import soundfile as sf
import numpy as np

# Directories
SOURCE_DIR = Path("My Voice Islamic")
TRAINING_DIR = Path("app/voice/voice_training")
REF_DIR = Path("app/voice/ref")

TRAINING_DIR.mkdir(parents=True, exist_ok=True)

# Audio files to process
AUDIO_FILES = [
    ("Haddan Teachings.mp3", SOURCE_DIR / "Haddan Teachings.mp3"),
    ("BE HAPPY ALONE.mp4", TRAINING_DIR / "BE HAPPY ALONE AND STOP DEPENDING ON PEOPLE _ Mufti Menk.wav"),
    ("BAD HABITS.mp4", TRAINING_DIR / "how to stop,give up or get rid of bad habits_ _ mufti menk _ islamic lectures.wav"),
]

# Convert to 24kHz WAV
converted_files = []
for label, input_file in AUDIO_FILES:
    if not input_file.exists():
        print(f"⚠ Skipping (not found): {label}")
        continue

    output_file = TRAINING_DIR / f"{label.replace('.', '_')}_24k.wav"
    if output_file.exists():
        print(f"✓ Already converted: {output_file.name}")
        converted_files.append((label, output_file))
        continue

    print(f"Converting: {label} → 24kHz WAV")
    cmd = [
        "ffmpeg", "-i", str(input_file),
        "-acodec", "pcm_s16le", "-ar", "24000",
        str(output_file), "-y"
    ]
    subprocess.run(cmd, capture_output=True, check=False)

    if output_file.exists():
        size = output_file.stat().st_size / (1024*1024)
        print(f"  ✓ {size:.1f} MB")
        converted_files.append((label, output_file))
    else:
        print(f"  ✗ Failed to convert")

print(f"\n{len(converted_files)} files converted and ready for analysis")

# Analyze each file
analysis_results = []
for label, filepath in converted_files:
    try:
        audio, sr = sf.read(str(filepath))

        # Convert to mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        duration = len(audio) / sr
        rms = np.sqrt(np.mean(audio**2))
        peak = np.max(np.abs(audio))

        # Simple pitch estimation
        try:
            acf = np.correlate(audio, audio, mode='full')
            acf = acf[len(acf)//2:]
            acf = acf / (acf[0] + 1e-8)
            min_lag = int(sr / 150)
            max_lag = int(sr / 70)
            if max_lag > min_lag:
                peak_lag = np.argmax(acf[min_lag:max_lag]) + min_lag
                pitch = sr / peak_lag
            else:
                pitch = 75.0
        except:
            pitch = 75.0

        analysis_results.append({
            "file": filepath.name,
            "label": label,
            "duration_seconds": round(duration, 1),
            "pitch_hz": round(pitch, 1),
            "rms_level": round(rms, 4),
            "peak_level": round(peak, 3),
            "sample_rate": sr
        })

        print(f"\n{label}:")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Pitch: {pitch:.1f} Hz")
        print(f"  RMS: {rms:.4f}, Peak: {peak:.3f}")

    except Exception as e:
        print(f"Error analyzing {label}: {e}")

# Save analysis
analysis_file = TRAINING_DIR / "analysis.json"
analysis_file.write_text(json.dumps(analysis_results, indent=2))
print(f"\n✓ Analysis saved to {analysis_file.name}")

# Create reference clips from different parts
print("\nCreating reference clips from different parts of recordings...")
reference_clips = []

for label, filepath in converted_files:
    try:
        audio, sr = sf.read(str(filepath))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        duration = len(audio) / sr

        # Extract clips from different parts (beginning, middle, end)
        for part_name, start_ratio in [("intro", 0.05), ("middle", 0.45), ("outro", 0.85)]:
            start_s = duration * start_ratio
            end_s = start_s + 10  # 10-second clips

            if start_s + 10 > duration:
                continue  # Skip if not enough audio

            start_sample = int(start_s * sr)
            end_sample = int(end_s * sr)
            clip = audio[start_sample:end_sample]

            clip_name = f"{label.split('.')[0]}_{part_name}_ref.wav"
            clip_path = REF_DIR / clip_name

            sf.write(str(clip_path), clip, sr)
            reference_clips.append({
                "file": clip_name,
                "source": label,
                "part": part_name,
                "duration": 10.0,
                "start_time": round(start_s, 1)
            })
            print(f"  ✓ {clip_name}")

    except Exception as e:
        print(f"  Error creating clips from {label}: {e}")

# Save reference clip metadata
clips_file = TRAINING_DIR / "reference_clips.json"
clips_file.write_text(json.dumps(reference_clips, indent=2))

print(f"\n{'='*60}")
print(f"VOICE TRAINING PREPARATION COMPLETE")
print(f"{'='*60}")
print(f"✓ Converted: {len(converted_files)} files to 24kHz WAV")
print(f"✓ Created: {len(reference_clips)} reference clips (10s each)")
print(f"✓ Analysis: {analysis_file.name}")
print(f"✓ Reference clips ready for Chatterbox training")
print(f"\nBest reference for use:")
print(f"  - Use haddan_ref.wav (current best quality)")
print(f"  - Or try any of the new reference clips in app/voice/ref/")
print(f"  - Edit .env TTS_REF to switch between them")
print(f"{'='*60}")
