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


def test_generated_song_joins_the_end_of_the_setlist(monkeypatch, isolated_data_dir):
    import app
    lib = Library(isolated_data_dir)
    for song_id in ("a", "b", "fresh"):
        lib.add(Song(id=song_id, title=song_id, genre='jazz', mood='warm',
                     created=1, audio_path='song.mp3'))
    monkeypatch.setattr(app, 'library', lib)
    monkeypatch.setattr(app.pipeline, 'generate_song',
                        lambda *a, **k: (lib.get('fresh'), []))
    outputs = app.create_song('fresh', 'jazz', '', [], 'warm', 'Instrumental',
                              'Auto', 5, 0, 'Auto', 'Auto', '', 12, False, ['b', 'a'])
    assert outputs[3].value == ['b', 'a', 'fresh']


def test_library_thumbnails_are_small_webp_copies(monkeypatch, isolated_data_dir, tmp_path):
    import app
    from PIL import Image
    cover = tmp_path / "songs" / "x" / "cover.png"
    cover.parent.mkdir(parents=True)
    Image.new("RGB", (1024, 1024), (200, 40, 90)).save(cover)
    monkeypatch.setattr(app, 'library', Library(isolated_data_dir))
    thumb = app._thumb(str(cover))
    assert thumb.endswith('.webp')
    with Image.open(thumb) as im:
        assert max(im.size) == 512


def _live_inputs(title='Fresh Jazz'):
    return (title, 'jazz', '', [], 'warm', 'Instrumental', 'Auto', 5, 0, 'Auto', 'Auto',
            '', 20, False, [])


def test_live_create_shows_step_card_then_the_new_song(monkeypatch, isolated_data_dir):
    import time
    import app
    lib = Library(isolated_data_dir)
    song = Song(id='fresh', title='Fresh Jazz', genre='jazz', mood='warm',
                created=1, audio_path='song.mp3')
    lib.add(song)
    monkeypatch.setattr(app, 'library', lib)

    def fake_generate(*a, progress_cb=None, **k):
        progress_cb("Music (ACE-Step)")
        time.sleep(0.6)
        return song, []

    monkeypatch.setattr(app.pipeline, 'generate_song', fake_generate)
    updates = list(app.create_song_live(*_live_inputs()))
    assert any('Writing music… · step 2 of 3' in u[0] for u in updates[:-1])
    final = updates[-1]
    assert len(final) == 9 and final[1]['value'] == 'song.mp3'
    assert 'jk-card-pending' not in final[0] and 'Fresh Jazz' in final[0]


def test_live_create_shows_error_card_and_raises(monkeypatch, isolated_data_dir):
    import gradio as gr
    import pytest
    import app
    monkeypatch.setattr(app, 'library', Library(isolated_data_dir))

    def boom(*a, **k):
        raise RuntimeError("music service down")

    monkeypatch.setattr(app.pipeline, 'generate_song', boom)
    gen = app.create_song_live(*_live_inputs())
    seen = []
    with pytest.raises(gr.Error):
        for u in gen:
            seen.append(u[0])
    assert 'jk-card-error' in seen[-1]


def test_blank_title_is_named_by_the_llm(monkeypatch, isolated_data_dir):
    import app
    lib = Library(isolated_data_dir)
    monkeypatch.setattr(app, 'library', lib)
    monkeypatch.setattr(app.llm, 'write_title', lambda genre, mood: 'Harbor Lights')
    seen = {}

    def fake_generate(library, title, *a, **k):
        seen['title'] = title
        song = Song(id='h', title=title, genre='jazz', mood='warm', created=1,
                    audio_path='song.mp3')
        lib.add(song)
        return song, []

    monkeypatch.setattr(app.pipeline, 'generate_song', fake_generate)
    app.create_song(*_live_inputs(title=''))
    assert seen['title'] == 'Harbor Lights'
