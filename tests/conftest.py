"""Shared test fixtures: repo root on sys.path, isolated data dir per test."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_jukebox import config  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point every Library/asset path at a throwaway directory."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    return data


@pytest.fixture
def sample_song_dict():
    return {
        "id": "test-song-1",
        "title": "Probe Song",
        "genre": "synthwave",
        "mood": "neon nights",
        "created": 1_700_000_000.0,
        "audio_path": "/tmp/x.mp3",
        "cover_path": "/tmp/x.png",
        "lyrics": "[Chorus]\nShine on",
        "cover_prompt": "neon skyline",
        "music_prompt": "synthwave, neon nights",
        "meta": {"metas": {"bpm": 120, "keyscale": "C Major"}, "duration_requested": 12},
        "lyrics_mode": "AUTO_LYRICS",
    }
