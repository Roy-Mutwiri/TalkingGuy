"""Voice engines. Pick with TTS_ENGINE in .env:
   edge   -> Microsoft Edge online neural voices (free, no key, needs internet)   [default]
   kokoro -> local Kokoro-82M on the GPU (works offline)
   chatterbox -> local Chatterbox-Turbo on the GPU: expressive, performs [laugh] [sigh] [chuckle] ... tags (MIT)
"""
from __future__ import annotations

import os


def make_speaker(engine: str | None = None, **kwargs):
    engine = (engine or os.getenv("TTS_ENGINE", "edge")).lower()
    if engine == "kokoro":
        from .kokoro_tts import Speaker

        return Speaker(**kwargs)
    if engine == "chatterbox":
        from .chatterbox_voice import ChatterboxSpeaker

        return ChatterboxSpeaker(**kwargs)
    from .edge_voice import EdgeSpeaker

    return EdgeSpeaker(**kwargs)
