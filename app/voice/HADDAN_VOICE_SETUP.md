# Haddan Voice Setup - Multi-Source Training

## Overview
The Chatterbox-Turbo voice engine uses reference voice clips to synthesize your voice. This document describes the comprehensive voice training setup with multiple sources for better authenticity and consistency.

## Voice Training Sources
1. **Haddan Teachings.mp3** (36:40) - Original teaching recording
2. **BE HAPPY ALONE AND STOP DEPENDING ON PEOPLE** (22:50) - Motivational content
3. **How to stop/get rid of bad habits** (30:03) - Educational content

## Voice Characteristics
- **Pitch**: 74.8 Hz (warm, natural male voice)
- **Speech Rate**: 2.8-3.1 words/second (varies by content)
- **Sample Rate**: 24000 Hz (Chatterbox standard)
- **Format**: PCM WAV at 24kHz
- **Total Training Data**: 89+ minutes of voice

## Available Voice References

### Primary Reference (Recommended)
- **haddan_ref.wav** (938 KB) - Optimized for Chatterbox, stable synthesis

### Alternative References (for testing)
- **Haddan Teachings_clip.wav** - First 10s of original teaching material
- **BE HAPPY ALONE_clip.wav** - Extract from motivational content (energetic)
- **BAD HABITS_clip.wav** - Extract from teaching content (dynamic delivery)

Each reference clip is 10 seconds at 24kHz, carefully selected from different parts of the source material to capture different aspects of your natural speaking style.

## Files
- `haddan_ref.wav` - Current reference (recommended)
- `*_clip.wav` - Alternative reference clips for testing
- `voice_training/` - Directory with full-length converted audio files
- `ATTRIBUTION.json` - Metadata for all voice samples

## Configuration
The voice is active when these settings are in place:

### .env (Voice Settings)
```
TTS_ENGINE=chatterbox          # Use Chatterbox-Turbo for expressive synthesis
TTS_REF=app/voice/ref/haddan_ref.wav  # Use Haddan's voice as reference
```

## How It Works
1. **Chatterbox-Turbo** reads the reference voice characteristics (pitch, timbre, rhythm)
2. When synthesizing text, it:
   - Generates speech in the reference voice's style
   - Supports expressive tags: `[laughs]`, `[sighs]`, `[chuckles]`, etc.
   - Applies mood-based expression (teach, show, calm, excited, etc.)
3. The synthesized speech is streamed directly to the broadcast mic chain

## Features
- **Expressive**: Mood-based delivery with tone variation
- **Local**: Runs on GPU, works offline after initial model load
- **Low-Latency**: Real-time synthesis suitable for live streaming
- **Consistent**: Same voice for every stream segment

## Audio Output
- Device: Virtual Audio Cable (CABLE Input)
- Channel: Both stereo and mono compatible
- Gain: Adjustable via `TTS_GAIN` (.env)
- Music bed: Can be mixed with background music

## Fallback
If Chatterbox fails or GPU is unavailable, the system automatically falls back to:
- Edge voice (online, free Microsoft neural voices)
- Kokoro-82M (local, if TTS_ENGINE=kokoro)

## Testing Different Voice References

To compare voice quality, you can test each reference clip:

```bash
# List available references
python scripts/test_voice_refs.py

# Edit .env and change TTS_REF to test each one:
# TTS_REF=app/voice/ref/haddan_ref.wav                    # Current (recommended)
# TTS_REF=app/voice/ref/Haddan_Teachings_clip.wav         # Original teaching
# TTS_REF=app/voice/ref/BE_HAPPY_ALONE_clip.wav           # Energetic variant
# TTS_REF=app/voice/ref/BAD_HABITS_clip.wav               # Dynamic variant

# Run the app with your chosen reference
python -m app.run

# Listen on TikTok LIVE stream and evaluate:
# - Clarity and naturalness
# - Consistency across sentences
# - Emotion/expression quality
# - Overall likability
```

### Recommendation
Start with `haddan_ref.wav` (current default) - it was optimized for Chatterbox synthesis. 
Switch to alternatives only if you prefer different characteristics or want to experiment.

## Quality Tips
- Voice clips should be clear and focused (no background noise)
- Consistent speaking speed works best
- 8-15 second reference clips are optimal for Chatterbox
- Pitch should be stable (avoid wide pitch variation in clip)
- Multiple sources help capture natural voice variation

## Files to Replace
To use a different voice:
1. Convert your MP3/M4A to 24kHz WAV:
   ```
   ffmpeg -i "your_voice.mp3" -acodec pcm_s16le -ar 24000 "haddan_ref.wav"
   ```
2. Update `TTS_REF` in .env
3. Update ATTRIBUTION.json metadata

## For Development
The voice reference is used by:
- `app/voice/chatterbox_voice.py` - Main synthesis engine
- `app/voice/edge_voice.py` - Fallback/streaming base class

The Chatterbox system is from Resemble AI (MIT license) and available at:
https://github.com/resemble-ai/chatterbox
