"""Unit tests for the song-generation pipeline (all services mocked)."""
from pathlib import Path

import pytest

from ai_jukebox import http, pipeline
from ai_jukebox.library import Library, Song

AUDIO = b"ID3-fake-song"
COVER = b"\x89PNG\r\n\x1a\nfakecover"


def _install_fakes(monkeypatch, cover_ok=True, music_ok=True):
    import ai_jukebox.music as music_mod
    import ai_jukebox.image as image_mod
    import ai_jukebox.llm as llm_mod

    captured = {}

    def fake_lyrics(title, genre, mood, structure="ABABCB", vocal_style=""):
        captured["lyrics"] = (title, genre, mood, vocal_style)
        return "[Verse 1]\nHello world\n[Chorus]\nShine on"

    def fake_cover_prompt(title, genre, mood, lyrics):
        captured["cover_prompt"] = (title, lyrics[:20])
        return "vivid album art prompt"

    def fake_music(prompt, lyrics="", duration=30, audio_format="mp3",
                   thinking=False, model=None, vocal_language="en",
                   poll_every=5.0, timeout=420, bpm=None, key_scale=None,
                   time_signature=None):
        captured["music"] = (prompt, lyrics, duration, thinking, bpm, key_scale,
                             time_signature)
        if not music_ok:
            raise http.ServiceError("ACE-Step boom")
        return {"audio": AUDIO, "meta": {"metas": {"bpm": 110, "duration": float(duration)}}}

    def fake_cover(prompt, size="1024x1024", timeout=300):
        captured["cover"] = prompt
        if not cover_ok:
            raise http.ServiceError("FLUX boom")
        return {"image": COVER, "revised_prompt": "rev"}

    monkeypatch.setattr(llm_mod, "write_lyrics", fake_lyrics)
    monkeypatch.setattr(llm_mod, "write_cover_prompt", fake_cover_prompt)
    monkeypatch.setattr(music_mod, "generate_song", fake_music)
    monkeypatch.setattr(image_mod, "generate_cover", fake_cover)
    return captured


def test_generate_song_full_track_saved(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    captured = _install_fakes(monkeypatch)
    song, steps = pipeline.generate_song(lib, "Neon Afterglow", "synthwave", "neon nights",
                                         duration=20)
    assert song.audio_path and Path(song.audio_path).read_bytes() == AUDIO
    assert song.cover_path and Path(song.cover_path).read_bytes() == COVER
    assert song.lyrics_mode == "AUTO_LYRICS"
    assert lib.get(song.id) is not None
    names = [s.name for s in steps]
    assert names == ["lyrics", "cover-prompt", "music", "cover-art"]
    assert all(s.status == "ok" for s in steps)
    assert captured["music"][2] == 20 and captured["music"][3] is False


def test_generate_song_custom_lyrics(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    _install_fakes(monkeypatch)
    song, steps = pipeline.generate_song(lib, "T", "pop", "fun", custom_lyrics="  my own words  ")
    assert song.lyrics_mode == "CUSTOM_LYRICS"
    assert song.lyrics == "my own words"
    assert steps[0].detail == "Used custom lyrics"


def test_generate_song_styling_options_forwarded(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    captured = _install_fakes(monkeypatch)
    song, steps = pipeline.generate_song(
        lib, "Feels", "synthwave", "neon nights",
        energy=8, bpm=112, key_scale="G major", time_signature="3/4",
        vocal_style="Duet (two voices)",
    )
    prompt, _lyrics, _dur, _think, bpm, key, tsig = captured["music"][:7]
    assert bpm == 112 and key == "G major" and tsig == "3/4"
    # energy maps to a descriptor; vocal style is woven into the music prompt
    assert "upbeat" in prompt and "Duet (two voices)" in prompt
    # lyrics got the vocal-style instruction too
    assert captured["lyrics"][3] == "Duet (two voices)"
    assert song.lyrics_mode == "AUTO_LYRICS"


def test_instrumental_drops_vocal_style_from_prompt(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    captured = _install_fakes(monkeypatch)
    pipeline.generate_song(lib, "Pure", "ambient", "calm", vocal=False,
                           vocal_style="Gospel choir")
    prompt = captured["music"][0]
    assert "Gospel choir" not in prompt
    # instrumental: no lyrics stage ran at all (fakes recorded nothing)
    assert "lyrics" not in captured or captured["lyrics"][0] is None


def test_cover_failure_is_nonfatal(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    _install_fakes(monkeypatch, cover_ok=False)
    song, steps = pipeline.generate_song(lib, "T", "pop", "fun")
    assert song.cover_path is None
    assert lib.get(song.id) is not None  # track still saved
    cover_step = next(s for s in steps if s.name == "cover-art")
    assert cover_step.status == "failed"


def test_music_failure_aborts_without_saving(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    _install_fakes(monkeypatch, music_ok=False)
    with pytest.raises(http.ServiceError, match="ACE-Step"):
        pipeline.generate_song(lib, "T", "pop", "fun")
    assert lib.all() == []


def test_step_result_to_dict():
    r = pipeline.StepResult("music", "ok", "12s track", 3.5)
    assert r.to_dict() == {"name": "music", "status": "ok", "detail": "12s track",
                           "seconds": 3.5, "error": ""}


def test_instrumental_generation_skips_lyrics(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    captured = _install_fakes(monkeypatch)
    song, steps = pipeline.generate_song(lib, "T", "jazz", "calm", vocal=False)
    assert song.vocal is False
    assert song.lyrics == ""
    assert song.lyrics_mode == "INSTRUMENTAL"
    assert captured["music"][1] == ""  # no lyrics sent to ACE-Step
    assert steps[0].detail.startswith("Instrumental")
    assert all(s.status == "ok" for s in steps)


def test_progress_cb_reports_each_stage(isolated_data_dir, monkeypatch):
    lib = Library(str(isolated_data_dir))
    _install_fakes(monkeypatch)
    seen = []
    pipeline.generate_song(lib, "T", "pop", "fun", progress_cb=seen.append)
    assert seen == ["Lyrics", "Cover art prompt", "Music (ACE-Step)", "Cover art (FLUX)"]
