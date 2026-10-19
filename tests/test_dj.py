"""Unit tests for the DJ show builder."""
from ai_jukebox import dj
from ai_jukebox.library import Library, Song


def _song(i, title, genre="pop") -> Song:
    return Song(
        id=i, title=title, genre=genre, mood="m", created=1.0, audio_path=f"/tmp/{i}.mp3",
        cover_path=None, lyrics="", cover_prompt="", music_prompt="", meta={}, lyrics_mode="AUTO_LYRICS",
    )


def test_make_intro_writes_tts_file(monkeypatch, isolated_data_dir):
    monkeypatch.setattr(dj.llm, "write_dj_script", lambda prev, nxt, prev_g, nxt_g: "Welcome to the show!")
    monkeypatch.setattr(dj.tts, "synthesize", lambda text, **kw: b"ID3intro")
    lib = Library(str(isolated_data_dir))
    script, path = dj.make_intro(lib, None, _song("s1", "First"))
    assert script == "Welcome to the show!"
    assert path.exists()
    assert path.read_bytes() == b"ID3intro"


def test_make_intro_uses_previous_track(monkeypatch, isolated_data_dir):
    calls = {}
    def fake_script(prev_title, prev_genre, next_title, next_genre):
        calls.update(prev=prev_title, nxt=next_title)
        return "x"
    monkeypatch.setattr(dj.llm, "write_dj_script", fake_script)
    monkeypatch.setattr(dj.tts, "synthesize", lambda text, **kw: b"x")
    lib = Library(str(isolated_data_dir))
    prev, nxt = _song("p", "Old"), _song("n", "New track")
    dj.make_intro(lib, prev, nxt)
    assert calls["prev"] == "Old" and calls["nxt"] == "New track"


def test_build_show_alternates_intro_and_song(monkeypatch, isolated_data_dir):
    monkeypatch.setattr(dj.llm, "write_dj_script", lambda *a, **k: "script")
    monkeypatch.setattr(dj.tts, "synthesize", lambda text, **kw: b"ID3")
    lib = Library(str(isolated_data_dir))
    songs = [_song("s1", "A"), _song("s2", "B"), _song("s3", "C")]
    segments = dj.build_show(lib, songs)
    assert [s["kind"] for s in segments] == ["intro", "song"] * 3
    assert all("script" in s for s in segments[::2])
    assert segments[1]["label"] == "A · pop"
    assert segments[1]["audio"] == "/tmp/s1.mp3"


def test_make_intro_passes_voice_ref_to_tts(monkeypatch, isolated_data_dir):
    seen = {}
    monkeypatch.setattr(dj.llm, "write_dj_script", lambda *a, **k: "hi there")
    monkeypatch.setattr(
        dj.tts, "synthesize",
        lambda text, **kw: (seen.update(kw) or b"ID3"),
    )
    lib = Library(str(isolated_data_dir))
    dj.make_intro(lib, None, _song("vc", "VoiceClone"), voice_ref_b64="QUJD")
    assert seen.get("ref_audio_b64") == "QUJD"


def test_build_show_applies_voice_ref_to_all_intros(monkeypatch, isolated_data_dir):
    seen = []

    def fake_synth(text, **kw):
        seen.append(kw.get("ref_audio_b64"))
        return b"ID3"

    monkeypatch.setattr(dj.llm, "write_dj_script", lambda *a, **k: "s")
    monkeypatch.setattr(dj.tts, "synthesize", fake_synth)
    lib = Library(str(isolated_data_dir))
    dj.build_show(lib, [_song("a", "A"), _song("b", "B")], voice_ref_b64="QUJD")
    assert seen == ["QUJD", "QUJD"]
