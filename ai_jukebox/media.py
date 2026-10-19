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


# --------------------------------------------------------------------------- viz

def _mono_peaks(path: str, buckets: int = 220) -> list[float]:
    """Downmix an audio file to `buckets` normalized peak amplitudes (0..1)."""
    dec = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=RATE,
    )
    raw = dec.samples
    step = max(1, len(raw) // 2 // buckets)  # 2 bytes per sample (mono s16)
    peaks: list[float] = []
    for i in range(buckets):
        lo = i * step
        hi = min(lo + step, len(raw) // 2)
        window = raw[lo * 2: hi * 2]
        if not window:
            peaks.append(0.0)
            continue
        m = max(abs(int.from_bytes(window[j:j + 2], "little", signed=True))
                for j in range(0, len(window) - 1, 2))
        peaks.append(m / 32767.0)
    return peaks


def waveform_svg(path: str, width: int = 640, height: int = 120,
                 markers: list[tuple[float, str]] | None = None) -> str:
    """Mirrored-peak waveform as a flat SVG, optionally with cue-time markers.

    `markers` is a list of (seconds, label) — e.g. the show cue sheet — drawn
    as dashed vertical lines with small captions. Pure stdlib text output
    (no image dependencies); used inside the jukebox on-screen controls panel.
    """
    try:
        peaks = _mono_peaks(path)
    except Exception:
        return ""
    if not peaks or max(peaks) <= 0:
        return "<svg></svg>"

    mid = height / 2.0
    amp = (height - 16) / 2.0
    n = len(peaks)
    step_x = width / (n - 1) if n > 1 else width

    top = " ".join(
        f"{i * step_x:.1f},{mid - max(0.02, p) * amp:.1f}" for i, p in enumerate(peaks)
    )
    bottom = " ".join(
        f"{i * step_x:.1f},{mid + max(0.02, p) * amp:.1f}" for i, p in reversed(list(enumerate(peaks)))
    )
    parts = [
        "<svg viewBox='0 0 %d %d' width='100%%' xmlns='http://www.w3.org/2000/svg'>" % (width, height),
        "<polyline points='%s' fill='none' stroke='#a6503c' stroke-width='1.6' "
        "stroke-linejoin='round' opacity='0.95'/>" % top,
        "<polyline points='%s' fill='none' stroke='#a6503c' stroke-width='1.6' "
        "stroke-linejoin='round' opacity='0.95'/>" % bottom,
    ]
    if markers:
        fmt = _format_time
        for t_sec, label in markers:
            x = t_sec / 30.0 * width  # 30 s scale (shows are 20-40 s per segment)
            x = min(max(x, 2.0), width - 2.0)
            parts.append(
                "<line x1='%.1f' y1='4' x2='%.1f' y2='%d' stroke='#b8966a' "
                "stroke-width='1' stroke-dasharray='3 3'/>" % (x, x, height - 4)
            )
            parts.append(
                "<text x='%.1f' y='10' font-size='8' fill='#8a8172' "
                "text-anchor='middle'>%s</text>" % (x, label)
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _format_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
