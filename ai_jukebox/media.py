"""Mix a show's audio segments into one continuous WAV track.

No ffmpeg required: miniaudio decodes every segment (MP3/WAV) to identical
44.1 kHz stereo 16-bit PCM, we concatenate with small silence gaps, and the
stdlib `wave` module writes the result.

A single mixed file gives the player native play/pause/skip controls and
guarantees DJ speech and music play in sequence — automatically, with no
overlap.
"""
from __future__ import annotations

import wave
from pathlib import Path

import miniaudio

RATE = 44100
CHANNELS = 2
SAMPLE_WIDTH = 2  # signed 16-bit PCM
GAP_SECONDS = 0.35


def mix_show(segment_paths: list[str], out_path: str,
             gap_seconds: float = GAP_SECONDS) -> tuple[str, list[float]]:
    """Concatenate audio files into one WAV; returns (out_path, start_times).

    `start_times[i]` is the offset (seconds) of segment `i` inside the mix,
    which the UI uses to print a cue sheet.
    """
    if not segment_paths:
        raise ValueError("Nothing to mix: no show segments.")

    gap_bytes = int(gap_seconds * RATE) * CHANNELS * SAMPLE_WIDTH
    silence = b"\x00" * gap_bytes

    frames = bytearray()
    starts: list[float] = []
    t = 0.0
    for i, path in enumerate(segment_paths):
        if i:
            frames.extend(silence)
            t += gap_seconds
        starts.append(t)
        dec = miniaudio.decode_file(
            str(path),
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=CHANNELS,
            sample_rate=RATE,
        )
        frames.extend(dec.samples)
        t += dec.num_frames / dec.sample_rate

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    return str(out), starts
