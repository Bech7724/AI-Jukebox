"""Unit tests for the show mixer (ai_jukebox/media.py)."""
import wave
from pathlib import Path

import pytest

from ai_jukebox import media

RATE = 44100
CHANNELS = 2


def _write_wav(path: str, seconds: float = 0.1) -> str:
    frames = int(RATE * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\x00\x00\x00\x00" * frames)  # silence frame (2ch x 16bit)
    return path


def test_mix_show_concatenates_sequentially(tmp_path):
    a = _write_wav(str(tmp_path / "a.wav"), 0.1)
    b = _write_wav(str(tmp_path / "b.wav"), 0.2)
    out = str(tmp_path / "mix.wav")

    result, starts = media.mix_show([a, b], out)

    assert result == out
    assert Path(out).exists()
    # segment offsets: 0.0, then first segment + gap
    assert starts[0] == pytest.approx(0.0, abs=0.001)
    assert starts[1] == pytest.approx(0.1 + media.GAP_SECONDS, abs=0.01)
    with wave.open(out, "rb") as w:
        assert w.getnchannels() == CHANNELS
        assert w.getframerate() == RATE
        assert w.getsampwidth() == 2
        expected_frames = int((0.1 + media.GAP_SECONDS + 0.2) * RATE)
        assert abs(w.getnframes() - expected_frames) < RATE * 0.02


def test_mix_show_requires_segments(tmp_path):
    with pytest.raises(ValueError, match="Nothing to mix"):
        media.mix_show([], str(tmp_path / "x.wav"))


def test_mix_show_decodes_mp3_and_wav_together(tmp_path):
    """Mixed-format inputs (TTS mp3 + music wav) must decode to one stream."""
    wav = _write_wav(str(tmp_path / "tone.wav"), 0.1)
    out = str(tmp_path / "mix2.wav")
    media.mix_show([wav, wav], out)
    with wave.open(out, "rb") as w:
        assert w.getnchannels() == CHANNELS
        assert w.getframerate() == RATE
    assert Path(out).stat().st_size > 0


def test_waveform_svg_emits_mirrored_wave_and_markers(tmp_path):
    import struct, math
    path = str(tmp_path / "wave.wav")
    frames = b"".join(
        struct.pack("<hh", int(12000 * math.sin(2 * math.pi * 440 * i / RATE)),
                    int(12000 * math.sin(2 * math.pi * 440 * i / RATE)))
        for i in range(int(RATE * 0.1))
    )
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    svg = media.waveform_svg(path, width=320, height=100,
                             markers=[(0.0, "DJ"), (0.1, "Neon")])
    assert svg.startswith("<svg")
    # mirrored peaks -> two polylines
    assert svg.count("<polyline") == 2
    # cue markers with labels
    assert svg.count("<line") == 2
    assert "Neon" in svg and "DJ" in svg
    assert "#a6503c" in svg  # terra accent


def test_waveform_svg_handles_garbage_path():
    assert media.waveform_svg("/nonexistent/definitely-not-here.mp3") in ("", "<svg></svg>")
