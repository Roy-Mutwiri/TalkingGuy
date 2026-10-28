#!/usr/bin/env python
"""Test different voice reference clips to find the best one for Chatterbox."""
import asyncio
from pathlib import Path
import os
from dotenv import load_dotenv

async def test_voices():
    """Synthesize test text with different voice references."""
    load_dotenv(Path(".env"))

    # Reference clips to test
    refs = [
        "app/voice/ref/haddan_ref.wav",
        "app/voice/ref/Haddan Teachings_clip.wav",
        "app/voice/ref/BE HAPPY ALONE_clip.wav",
        "app/voice/ref/BAD HABITS_clip.wav",
    ]

    # Test text
    test_text = "Welcome to the Chart Room. Today we're looking at support and resistance levels."

    print("="*60)
    print("VOICE REFERENCE TESTING")
    print("="*60)
    print(f"Test phrase: \"{test_text}\"\n")

    available_refs = [r for r in refs if Path(r).exists()]

    if not available_refs:
        print("❌ No reference clips found!")
        return

    print(f"Found {len(available_refs)} reference clips to test:\n")

    for i, ref in enumerate(available_refs, 1):
        ref_name = Path(ref).name
        ref_size = Path(ref).stat().st_size / 1024
        print(f"{i}. {ref_name} ({ref_size:.0f} KB)")
        print(f"   Set in .env: TTS_REF={ref}")
        print()

    print("="*60)
    print("TESTING INSTRUCTIONS:")
    print("="*60)
    print("To test each voice reference:")
    print("1. Edit .env and set TTS_REF to one of the paths above")
    print("2. Run: python -m app.run")
    print("3. Listen to the stream on TikTok")
    print("4. Compare audio quality and naturalness")
    print("5. Choose the best one and keep it in .env")
    print()
    print("Recommended testing order:")
    print("• haddan_ref.wav (current - established)")
    print("• Haddan Teachings_clip.wav (original audio)")
    print("• BE HAPPY ALONE_clip.wav (energetic)")
    print("• BAD HABITS_clip.wav (varied pace)")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_voices())
