"""Client for the class Chatterbox TTS service (port 9008).

Custom FastAPI wrapper around Chatterbox Multilingual V3. POST
/v1/audio/speech with {"model": "chatterbox-v3", "input": …} returns a
complete audio file (MP3 by default). Verified against the live service.
"""
from __future__ import annotations

from . import config, http


def synthesize(text: str, voice: str = "default", language_id: str = "en",
               response_format: str = "mp3", speed: float = 1.0,
               ref_audio_b64: str | None = None, timeout: int = 300) -> bytes:
    """Turn text into speech; returns the encoded audio bytes.

    `ref_audio_b64` — optional base64 MP3/WAV snippet used for voice
    cloning with the built-in default voice (per the service schema:
    "Use with voice='default'". No URLs or paths.)
    """
    payload = {
        "model": config.TTS_MODEL,
        "input": text,
        "voice": voice,
        "language_id": language_id,
        "response_format": response_format,
        "speed": speed,
    }
    if ref_audio_b64:
        payload["voice"] = "default"  # cloning rides on the default voice slot
        payload["ref_audio"] = ref_audio_b64
    audio = http.post_raw(
        f"{config.base_url(config.TTS_PORT)}/v1/audio/speech", payload, timeout=timeout
    )
    if not audio:
        raise http.ServiceError("TTS returned empty audio.")
    return audio
