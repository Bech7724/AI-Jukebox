"""Unit tests for the on-disk song library."""
from pathlib import Path

from ai_jukebox.library import Library, Song


def _song(i="abc123", title="Tune") -> Song:
    return Song(
        id=i, title=title, genre="pop", mood="bright", created=1000.0,
        audio_path="/tmp/a.mp3", cover_path=None,
        lyrics="", cover_prompt="", music_prompt="", meta={"metas": {"bpm": 90}}, lyrics_mode="AUTO_LYRICS",
    )


def test_add_and_get_roundtrip(isolated_data_dir):
    lib = Library(str(isolated_data_dir))
    lib.add(_song())
    got = lib.get("abc123")
    assert got is not None
    assert got.title == "Tune"
    assert got.music_metas["bpm"] == 90
    assert got.to_dict()["id"] == "abc123"


def test_all_sorted_newest_first(isolated_data_dir):
    lib = Library(str(isolated_data_dir))
    a = _song("a", "Old"); a.created = 100.0
    b = _song("b", "New"); b.created = 200.0
    lib.add(a); lib.add(b)
    assert [s.id for s in lib.all()] == ["b", "a"]


def test_delete_removes_index_and_assets(isolated_data_dir):
    lib = Library(str(isolated_data_dir))
    song = _song()
    lib.add(song)
    song_dir = lib.song_dir(song.id)
    song_dir.mkdir(parents=True, exist_ok=True)
    (song_dir / "song.mp3").write_bytes(b"x")
    assert lib.delete("abc123") is True
    assert lib.get("abc123") is None
    assert not song_dir.exists()
    assert lib.delete("abc123") is False


def test_from_dict_ignores_unknown_keys(isolated_data_dir):
    lib = Library(str(isolated_data_dir))
    d = _song().to_dict()
    d["unexpected_key"] = 42
    assert Song.from_dict(d).id == "abc123"


def test_slugify_sanitizes():
    from ai_jukebox.library import slugify
    assert slugify("Neon Afterglow!!") == "neon-afterglow"
    assert slugify("!!!") == "song"


def test_new_song_id_is_unique():
    ids = {Library.new_song_id("Same Title") for _ in range(50)}
    assert len(ids) == 50


def test_seed_samples_copies_bundled_tracks(isolated_data_dir, sample_song_dict):
    lib = Library(str(isolated_data_dir))
    samples = Path(isolated_data_dir.parent) / "samples"
    samples.mkdir(parents=True, exist_ok=True)

    entry = dict(sample_song_dict)
    entry["id"] = "probe-song-1"
    entry["audio_path"] = "probe-song-1/song.mp3"
    entry["cover_path"] = "probe-song-1/cover.png"
    (samples / "probe-song-1").mkdir(parents=True, exist_ok=True)
    (samples / "probe-song-1" / "song.mp3").write_bytes(b"ID3sample")
    (samples / "probe-song-1" / "cover.png").write_bytes(b"PNGSAMPLE")
    (samples / "library.json").write_text(
        __import__("json").dumps([entry], indent=2)
    )

    from ai_jukebox.library import seed_samples

    assert seed_samples(lib, samples_root=samples) == 1
    song = lib.get("probe-song-1")
    assert song is not None
    assert Path(song.audio_path).read_bytes() == b"ID3sample"
    assert Path(song.cover_path).read_bytes() == b"PNGSAMPLE"

    # second call: library non-empty -> no reseed
    assert seed_samples(lib, samples_root=samples) == 0


def test_seed_samples_noop_without_bundle(isolated_data_dir):
    from ai_jukebox.library import seed_samples

    lib = Library(str(isolated_data_dir))
    assert seed_samples(lib, samples_root=isolated_data_dir / "missing") == 0
