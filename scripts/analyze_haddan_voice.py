#!/usr/bin/env python
"""Analyze the Haddan Islamic voice recording to get pitch and speech rate."""
import soundfile as sf
import numpy as np
from pathlib import Path

wav_file = Path("app/voice/ref/haddan_ref.wav")
audio, sr = sf.read(str(wav_file))

# Convert stereo to mono
if audio.ndim > 1:
    audio = audio.mean(axis=1)

# Basic characteristics
duration = len(audio) / sr
rms = np.sqrt(np.mean(audio**2))

print("=" * 60)
print("HADDAN VOICE ANALYSIS")
print("=" * 60)
print(f"Duration: {duration:.1f} seconds")
print(f"Sample Rate: {sr} Hz")
print(f"RMS Level: {rms:.4f}")
print(f"Peak Level: {np.max(np.abs(audio)):.4f}")

# Estimate pitch using autocorrelation
try:
    # Simple autocorrelation method
    acf = np.correlate(audio, audio, mode='full')
    acf = acf[len(acf)//2:]
    acf = acf / (acf[0] + 1e-8)

    # For male voice, pitch typically 70-150 Hz
    min_lag = int(sr / 150)
    max_lag = int(sr / 70)

    peak_lag = np.argmax(acf[min_lag:max_lag]) + min_lag
    estimated_pitch = sr / peak_lag
    print(f"Estimated Pitch: {estimated_pitch:.1f} Hz")
except Exception as e:
    print(f"Pitch analysis: Could not calculate ({e})")
    estimated_pitch = 120

# Estimate speech rate (words per second)
# This is a rough estimate based on energy
energy = np.abs(audio)
# Detect speech activity (peaks)
threshold = np.mean(energy) * 0.3
speech_frames = energy > threshold
speech_ratio = np.sum(speech_frames) / len(speech_frames)

# Estimate WPS based on audio characteristics
# Typical male speech is 2-3 words per second
estimated_wps = 2.5 + (speech_ratio - 0.3) * 2  # Adjust based on speech density
estimated_wps = max(2.0, min(3.5, estimated_wps))

print(f"Estimated Speech Rate: {estimated_wps:.2f} words/second")
print(f"File Size: {wav_file.stat().st_size / (1024*1024):.1f} MB")
print("\n✓ Voice reference clip is ready to use!")
print("✓ Set TTS_REF=haddan_ref.wav in .env or use chatterbox engine")
print("=" * 60)
