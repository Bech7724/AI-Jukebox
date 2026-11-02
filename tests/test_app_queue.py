"""The UI must hand the DJ the selected order, including a shuffled queue."""
from ai_jukebox.library import Library, Song


def test_show_uses_selected_order_not_library_recency(monkeypatch, isolated_data_dir):
    import app

    lib = Library(isolated_data_dir)
    for song_id, created in (("old", 1), ("new", 2)):
        lib.add(Song(id=song_id, title=song_id, genre="pop", mood="warm",
                     created=created, audio_path=f"{song_id}.mp3"))
    monkeypatch.setattr(app, "library", lib)
    seen = []

    def fake_show(library, songs, **kwargs):
        seen.append([s.id for s in songs])
        return [{"kind": "song", "label": s.title, "audio": s.audio_path}
                for s in songs]

    monkeypatch.setattr(app.dj, "build_show", fake_show)
    monkeypatch.setattr(app.media, "mix_show", lambda *a: ("mix.wav", [0, 20]))
    monkeypatch.setattr(app, "_viz_html", lambda *a: "")
    app.build_show(["old", "missing", "new"], None)
    app.build_show(["new", "old"], None)
    assert seen == [["old", "new"], ["new", "old"]]


def test_generated_song_immediately_updates_library_table(monkeypatch, isolated_data_dir):
    import app
    lib = Library(isolated_data_dir)
    song = Song(id='fresh', title='Fresh Jazz', genre='jazz', mood='warm',
                created=1, audio_path='song.mp3')
    lib.add(song)
    monkeypatch.setattr(app, 'library', lib)
    monkeypatch.setattr(app.pipeline, 'generate_song', lambda *a, **k: (song, []))
    outputs = app.create_song('Fresh Jazz', 'jazz', '', [], 'warm', 'Instrumental',
                              'Auto', 5, 0, 'Auto', 'Auto', '', 12, False, [])
    assert len(outputs) == 8
    assert outputs[-1].value['data'][0][0] == 'Fresh Jazz'
