"""AI Jukebox — Gradio UI (single screen).

One page, three sections:
  1. Create a song — style, mood, duration, vocal|instrumental; the app
     writes lyrics (9001), produces the track (9007), and paints cover art
     (9006). Progress is reported step by step; failures show a clear error
     and the Generate button is always ready to retry.
  2. Playback queue — pick tracks (in queue order), optionally upload an
     MP3/WAV voice reference to clone the DJ's voice (blank = default);
     Build the show mixes Qwen-written, Chatterbox-spoken DJ commentary
     (9001 + 9008) between songs into ONE continuous track. The player has
     play/pause/skip controls; the queue advances automatically and speech
     never overlaps music. A cue sheet lists every segment with its start
     time and the covers of the queued tracks.
  3. Library — titles + matching covers, metadata, delete/refresh.

Three pre-generated sample tracks ship under samples/ (AI-written lyrics
only) and are seeded into the library on first run.

Every AI feature runs on the class services. Port 9000 is reserved for
agentic use and is never touched by this app. Real credentials live only in
the developer's local .env (gitignored); user uploads and generated content
stay inside the local gitignored data/ tree.
"""
from __future__ import annotations

import base64
import inspect
import os
import random
import threading
import time
from html import escape
from pathlib import Path

import gradio as gr

from ai_jukebox import dj, llm, media, pipeline
from ai_jukebox.library import Library, seed_samples

library = Library()
_seeded = seed_samples(library)

LIBRARY_HEADERS = ["Title", "Genre", "Mood", "Type", "BPM", "Key", "Created"]


# ---------------------------------------------------------------- helpers

def _song_choices() -> list[tuple[str, str]]:
    return [(f"{s.title} — {s.genre}", s.id) for s in library.all()]


def _track_type(song) -> str:
    return "Instrumental" if not song.vocal else "Vocal"


def _library_rows() -> list[list]:
    rows = []
    for s in library.all():
        m = s.music_metas
        bpm = m.get("bpm")
        key = m.get("keyscale")
        rows.append(
            [
                s.title,
                s.genre,
                s.mood,
                _track_type(s),
                f"{bpm} bpm" if bpm not in (None, "") else "—",
                key or "—",
                time.strftime("%Y-%m-%d %H:%M", time.localtime(s.created)),
            ]
        )
    return rows


def _thumb(path: str | None) -> str | None:
    """512px WebP copy of a cover for grids; full covers are ~3 MB PNGs.

    Thumbnails are cached under the (gitignored) data dir and rebuilt when the
    cover changes. Falls back to the original file if conversion fails.
    """
    if not path:
        return path
    src = Path(path)
    dst = library.root / "thumbs" / f"{src.parent.name}-{src.stem}.webp"
    try:
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            from PIL import Image  # installed with gradio
            dst.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im.thumbnail((512, 512))
                im.save(dst, "WEBP", quality=82)
        return str(dst)
    except Exception:
        return path


def _covered_songs():
    return [s for s in library.all() if s.cover_path]


def _library_gallery_items():
    return [(_thumb(s.cover_path), f"{s.title} — {s.genre} ({_track_type(s)})")
            for s in _covered_songs()]


# ------------------------------------------------- studio: latest-tracks grid

_URI_CACHE: dict[tuple[str, float], str] = {}
_PLAY_SVG = ("<svg viewBox='0 0 24 24' width='16' height='16' aria-hidden='true'>"
             "<path d='M8 5.5v13l11-6.5z' fill='currentColor'/></svg>")
_STUDIO_CARDS = 4

# Pipeline step names -> (step number of 3, friendly label) for the live card.
_LIVE_STEPS = {
    "Starting…": (1, "Getting started"),
    "Naming": (1, "Naming your song"),
    "Lyrics": (1, "Writing lyrics"),
    "Cover art prompt": (1, "Sketching the cover idea"),
    "Music (ACE-Step)": (2, "Writing music"),
    "Cover art (FLUX)": (3, "Painting the cover"),
}


def _thumb_uri(path: str | None) -> str:
    """Inline data URI of a cover thumbnail, so the HTML grid needs no file route."""
    thumb = _thumb(path)
    if not thumb or not Path(thumb).exists():
        return ""
    key = (thumb, Path(thumb).stat().st_mtime)
    if key not in _URI_CACHE:
        mime = "image/webp" if thumb.endswith(".webp") else "image/png"
        _URI_CACHE[key] = f"data:{mime};base64," + base64.b64encode(Path(thumb).read_bytes()).decode()
    return _URI_CACHE[key]


def _studio_grid_html(pending: tuple[str, int, str] | None = None, error: str | None = None) -> str:
    """Latest tracks as cards. `pending` = (title, step, label) adds a live card first."""
    cards = []
    if pending:
        title, step, label = pending
        cards.append(
            "<div class='jk-card jk-card-pending'>"
            "<div class='jk-card-art'><span class='jk-spinner'></span></div>"
            f"<div class='jk-card-title'>{escape(title)}</div>"
            f"<div class='jk-card-meta'>{escape(label)}… · step {step} of 3</div>"
            f"<div class='jk-card-bar'><i style='width:{int(step / 3 * 100)}%'></i></div>"
            "</div>")
    elif error:
        cards.append(
            "<div class='jk-card jk-card-error'>"
            "<div class='jk-card-art'>!</div>"
            "<div class='jk-card-title'>Couldn't make this song</div>"
            f"<div class='jk-card-meta'>{escape(error[:140])}</div>"
            "</div>")
    for s in library.all()[: _STUDIO_CARDS - len(cards)]:
        art = _thumb_uri(s.cover_path)
        img = f"<img src='{art}' alt=''>" if art else "<span class='jk-card-noart'>♪</span>"
        cards.append(
            f"<button class='jk-card' type='button' onclick=\"jkPick('{escape(s.id)}')\" "
            f"title='Play {escape(s.title)}'>"
            f"<div class='jk-card-art'>{img}<span class='jk-card-play'>{_PLAY_SVG}</span></div>"
            f"<div class='jk-card-title'>{escape(s.title)}</div>"
            f"<div class='jk-card-meta'>{escape(s.genre)} · {_track_type(s)}</div>"
            "</button>")
    return ("<div class='jk-sub'>Your latest tracks</div>"
            f"<div class='jk-grid'>{''.join(cards)}</div>")


def create_song_live(*inputs):
    """Run create_song in a worker thread and stream a live status card.

    Yields the studio grid first (with the pending card) and leaves the other
    outputs untouched until the song is ready.
    """
    title = (inputs[0] or "").strip() or "New song"
    state = {"desc": "Starting…"}

    def progress(_fraction=None, desc=None, **_):
        if desc:
            state["desc"] = desc

    box: dict = {}

    def run():
        try:
            box["out"] = create_song(*inputs, progress=progress)
        except Exception as e:  # handed back to the UI thread below
            box["err"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    shown = None
    while worker.is_alive():
        if state["desc"] != shown:
            shown = state["desc"]
            step, label = _LIVE_STEPS.get(shown, (1, "Working"))
            yield (_studio_grid_html(pending=(title, step, label)),) + (gr.skip(),) * 8
        worker.join(0.25)
    if "err" in box:
        err = box["err"]
        yield (_studio_grid_html(error=getattr(err, "message", None) or str(err)),) + (gr.skip(),) * 8
        raise box["err"]
    audio, *rest = box["out"]
    newest = next((s for s in library.all() if s.audio_path == audio), None)
    label = f"Now previewing · {newest.title}" if newest else "Now previewing"
    yield (_studio_grid_html(), gr.update(value=audio, label=label, visible=True)) + tuple(rest)


def play_pick(value: str):
    """Card click from the studio grid -> load that track into the studio player."""
    song = library.get((value or "").split("|")[0])
    if not song:
        return gr.skip()
    return gr.update(value=song.audio_path, label=f"Now previewing · {song.title}", visible=True)


def preview_track(evt: gr.SelectData):
    """Play the library track whose cover was clicked."""
    songs = _covered_songs()
    if evt.index is None or evt.index >= len(songs):
        return gr.update(visible=False)
    song = songs[evt.index]
    return gr.update(value=song.audio_path, label=f"Preview · {song.title}", visible=True)


def _df_update() -> gr.Dataframe:
    return gr.Dataframe(value=_library_rows(), headers=LIBRARY_HEADERS, type="array", interactive=False)


def _dropdown_update() -> gr.Dropdown:
    return gr.Dropdown(choices=_song_choices(), value=None)


def _picker_update(value=None) -> gr.Dropdown:
    """Dropdown refresh that preserves a selectable value (queue order)."""
    return gr.Dropdown(choices=_song_choices(), value=value or None)


def _gallery_update(columns=4) -> gr.Gallery:
    return gr.Gallery(value=_library_gallery_items(), columns=columns, height="auto")


def _voice_ref_b64(path: str | None) -> str | None:
    """Read an uploaded voice reference and base64 it for Chatterbox cloning."""
    if not path:
        return None
    return base64.b64encode(Path(path).read_bytes()).decode()


_STEP_FRACTIONS = {
    "Lyrics": 0.15, "Cover art prompt": 0.30,
    "Music (ACE-Step)": 0.45, "Cover art (FLUX)": 0.78,
}


# ------------------------------------------------------------ section 1: create

GENRES = [
    "upbeat indie pop", "synthwave", "lo-fi hip hop", "jazz", "bossa nova",
    "acoustic folk", "indie rock", "rock", "alternative rock", "pop", "R&B",
    "soul", "funk", "disco", "house", "techno", "EDM", "drum & bass",
    "hip hop", "trap", "country", "bluegrass", "folk", "blues", "metal",
    "classical", "ambient", "cinematic", "reggae", "ska", "world music",
    "Custom…",
]
MOODS = [
    "chill", "energetic", "melancholic", "romantic", "hopeful", "dark",
    "dreamy", "nostalgic", "aggressive", "warm", "longing", "celebratory",
    "mysterious", "peaceful",
]
VOCAL_STYLES = [
    "Auto", "Soft female vocalist", "Bright male vocalist",
    "Duet (two voices)", "Gospel choir", "Soulful rasp",
    "Whispery intimate", "Belting power",
]
KEYS = ["Auto", "C major", "G major", "D major", "A major", "E major",
        "F major", "B♭ major", "A minor", "E minor", "D minor", "G minor"]
TIME_SIGNATURES = ["Auto", "3/4", "4/4", "6/8"]


def create_song(title, genre_choice, genre_custom, mood_multi, mood_custom,
                vocal_choice, vocal_style, energy, bpm, key_choice, tsig_choice,
                custom_lyrics, duration, thinking, queue, progress=gr.Progress()):
    title = (title or "").strip()
    genre = genre_choice if genre_choice and genre_choice != "Custom…" else (
        (genre_custom or "").strip() or "upbeat indie pop")
    mood_parts = [m for m in (mood_multi or []) if m]
    if (mood_custom or "").strip():
        mood_parts.append(mood_custom.strip())
    mood = ", ".join(mood_parts) or "hopeful and sunny"
    vocal = vocal_choice == "Vocal"
    progress(0.05, desc="Starting…")
    if not title:  # blank title: Qwen names it from the style and description
        progress(0.08, desc="Naming")
        try:
            title = llm.write_title(genre, mood)
        except Exception:
            title = "Untitled Song"
    try:

        def _cb(name: str) -> None:
            progress(_STEP_FRACTIONS.get(name, 0.5), desc=name)

        song, steps = pipeline.generate_song(
            library, title, genre, mood,
            duration=int(duration),
            custom_lyrics=custom_lyrics,
            thinking=bool(thinking),
            vocal=vocal,
            progress_cb=_cb,
            energy=int(energy),
            bpm=int(bpm) if bpm and int(bpm) > 0 else None,
            key_scale=None if key_choice == "Auto" else key_choice,
            time_signature=None if tsig_choice == "Auto" else tsig_choice,
            vocal_style=vocal_style,
        )
    except Exception as e:  # surfaced in the UI, never the terminal; retry is one click
        progress(0.0, desc="Failed")
        raise gr.Error(
            f"Generation failed — nothing was saved. Check the class services "
            f"and retry: {e}"
        ) from e
    progress(1.0, desc="Done")

    lines = [f"### {song.title}", f"**{song.genre}** · {song.mood} · **{_track_type(song)}**", ""]
    if song.lyrics:
        src = "custom lyrics" if song.lyrics_mode == "CUSTOM_LYRICS" else "written by class LLM (9001)"
        lines.append(f"**Lyrics** ({src}):")
        lines.append(f"```\n{song.lyrics}\n```")
    else:
        lines.append("_Instrumental track — no vocals._")
    lines.append("**Production log**")
    for s in steps:
        mark = "✅" if s.status == "ok" else "⚠️"
        lines.append(f"- `{s.name}` {mark} {s.detail or s.error} ({s.seconds:.1f}s)")
    lines.append("\n_Track added to the library and to the DJ Booth setlist._")
    queue_ids = [i for i in (library.prune_ids(queue) or []) if i != song.id] + [song.id]
    return (song.audio_path, song.cover_path, "\n".join(lines),
            _picker_update(value=queue_ids),
            _gallery_update(), _dropdown_update(), _dropdown_update(), _df_update())


# -------------------------------------------------------- section 2: queue + DJ

def _format_ts(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def build_show(selected_ids, voice_ref):
    songs = [s for s in library.all() if s.id in (selected_ids or [])]
    if not songs:
        return (None, gr.Gallery(value=[], visible=False),
                "⚠️ Pick at least one track, then press **Build the show**.",
                _viz_html("", []))
    # Preserve the order in which the user selected tracks (the queue order).
    order = {song_id: i for i, song_id in enumerate(selected_ids or [])}
    songs.sort(key=lambda s: order[s.id])

    try:
        segments = dj.build_show(library, songs, voice_ref_b64=_voice_ref_b64(voice_ref))
    except Exception as e:
        raise gr.Error(
            f"Show build failed (DJ script or voice unavailable) — check the "
            f"class services and retry: {e}"
        ) from e
    try:
        show_path = library.root / "shows" / f"show-{int(time.time())}.wav"
        mixed, starts = media.mix_show([s["audio"] for s in segments], str(show_path))
    except Exception as e:
        raise gr.Error(f"Could not mix the show: {e}") from e

    voice_note = "custom (from your upload)" if voice_ref else "default Chatterbox voice"
    lines = [f"Show ready · DJ voice: **{voice_note}**. Plays straight through, no overlaps."]
    for seg, t in zip(segments, starts):
        prefix = "DJ intro" if seg["kind"] == "intro" else seg['label']
        lines.append(f"- `{_format_ts(t)}` {prefix}")
    gallery_items = [
        (_thumb(s.cover_path), f"{s.title} — {s.genre} ({_track_type(s)})")
        for s in songs if s.cover_path
    ]
    viz = _viz_html(
        mixed,
        [(t, "DJ" if seg["kind"] == "intro" else seg["label"].split(" · ")[0])
         for seg, t in zip(segments, starts)],
    )
    return (
        mixed,
        gr.Gallery(value=gallery_items, columns=max(1, min(len(gallery_items), 6)),
                   visible=bool(gallery_items)),
        "\n".join(lines),
        viz,
    )


# ----------------------------------------------------------- section 3: library

def delete_song(song_id, queue):
    if song_id:
        library.delete(song_id)
    kept = library.prune_ids(queue)
    return (_df_update(), _picker_update(value=kept), _dropdown_update(),
            _dropdown_update(), _gallery_update())


def refresh_library(queue):
    kept = library.prune_ids(queue)
    return (_df_update(), _picker_update(value=kept), _dropdown_update(),
            _dropdown_update(), _gallery_update())


# ----------------------------------------------------------- fun + polish



SURPRISE_DESCRIPTIONS = [
    "A late-night drive through a quiet, rain-soaked city",
    "First chairlift up the mountain on a bluebird powder day",
    "Dancing barefoot at a summer bonfire with old friends",
    "Coffee and a notebook on a slow Sunday morning",
    "Leaving home for the first time, scared and excited",
    "Neon arcade lights and a high score at 2 a.m.",
]


def surprise_me():
    """One click: random description + full styling. The title is left blank so
    Qwen names the song to match the description."""
    moods = random.sample(MOODS, k=random.randint(1, 3))
    return (
        gr.update(value=""),
        gr.update(value=random.choice([g for g in GENRES if g != "Custom…"])),
        gr.update(value=moods),
        gr.update(value=random.randint(1, 10)),
        gr.update(value=random.choice([0, 80, 92, 104, 116, 128, 140, 152])),
        gr.update(value=random.choice(KEYS)),
        gr.update(value=random.choice(TIME_SIGNATURES)),
        gr.update(value=random.choice(VOCAL_STYLES)),
        gr.update(value=random.choice(SURPRISE_DESCRIPTIONS)),
        gr.update(value="", visible=False),
    )


def shuffle_queue(selected):
    """Randomize the queue order (the DJ loves a mystery set)."""
    q = list(selected or [])
    random.shuffle(q)
    return gr.update(choices=_song_choices(), value=q or None)


def rename_song(song_id, new_title, queue):
    if song_id and new_title and new_title.strip():
        library.rename(song_id, new_title.strip())
    kept = library.prune_ids(queue)
    return (_df_update(), _picker_update(value=kept), _dropdown_update(),
            _dropdown_update(), _gallery_update(), gr.update(value=""))


# Client-side skip buttons: seek the continuous-mix player to the previous /
# next cue time. The cue list rides in data-cues on the panel div, so the JS
# needs no backend round-trip. (Native player seek still works as always.)
_SKIP_JS = ("function activeAudio(root){if(!root)return null;"
            "var audios=root.querySelectorAll('audio');"
            "for(var j=0;j<audios.length;j++){"
            "if(audios[j].currentSrc||audios[j].getAttribute('src'))return audios[j]}"
            "var nodes=root.querySelectorAll('*');"
            "for(var j=0;j<nodes.length;j++){if(nodes[j].shadowRoot){"
            "var found=activeAudio(nodes[j].shadowRoot);if(found)return found}}"
            "return null}"
            "var a=activeAudio(document.getElementById('show-player'));"
            "var box=document.getElementById('jukebox-controls');"
            "if(!a||!box)return;"
            "var cs=(box.getAttribute('data-cues')||'').split(',').map(parseFloat)"
            ".filter(function(x){return isFinite(x)});"
            "var t=a.currentTime||0,n=-1,i;"
            "if(d>0){for(i=0;i<cs.length;i++){if(cs[i]>t+0.6){n=i;break}}}"
            "else{for(i=cs.length-1;i>=0;i--){if(cs[i]<t-1.0){n=i;break}}}"
            "if(n>=0){a.currentTime=cs[n];if(a.paused)a.play().catch(function(){})}")

_BTN_TPL = (
    '<button class="jk-skip" onclick="(function(d){__SKIP__})(%d)">%s</button>'
)


def _viz_html(mix_path, markers):
    """Waveform of the mixed show + ⏮/⏭ skip buttons, as one HTML block."""
    if not mix_path or not markers:
        return (
            "<div id='jukebox-controls' class='jk-viz jk-viz-empty' data-cues=''>"
            "<div class='jk-viz-hint'>Build a show to see its waveform here. "
            "⏮ Prev / ⏭ Next jump between DJ intros and songs.</div></div>"
        )
    cues = ",".join(f"{t:.2f}" for t, _ in markers)
    svg = media.waveform_svg(mix_path, markers=markers)
    prev = _BTN_TPL.replace("__SKIP__", _SKIP_JS) % (-1, "⏮ Prev")
    nxt = _BTN_TPL.replace("__SKIP__", _SKIP_JS) % (1, "⏭ Next")
    return (
        f"<div id='jukebox-controls' class='jk-viz' data-cues='{cues}'>"
        f"<div class='jk-viz-wave'>{svg}</div>"
        f"<div class='jk-viz-btns'>{prev}{nxt}</div>"
        f"</div>"
    )


# ---------------------------------------------------------------------- UI

# Night-club jukebox theme: deep ink background, raised panels, neon pink
# accents with amber and cyan highlights. Light text on dark panels throughout,
# and the same values for Gradio's light and dark modes so the look is fixed.
_NIGHT = "#0c0a12"            # page background
_PANEL = "#16131f"            # cards
_PANEL_2 = "#1f1b2b"          # inputs, inner surfaces
_LINE = "#2e2942"             # borders
_TEXT = "#f2eefa"
_MUTED = "#a69fbc"
_NEON = "#ff4f8b"             # glow accent (sliders, focus, "on air"); never under text
_PRIMARY = "#e0306c"          # button fill: white text stays above 4.5:1 contrast
_PRIMARY_2 = "#d9452f"        # second stop of the button gradient
_PRIMARY_HOVER = "#c92a61"
_AMBER = "#ffb547"
_CYAN = "#4fe3ff"

_THEME_VALUES = dict(
    body_background_fill=_NIGHT,
    background_fill_primary=_PANEL,
    background_fill_secondary=_PANEL_2,
    block_background_fill=_PANEL,
    block_border_color=_LINE,
    block_label_background_fill=_PANEL_2,
    block_label_text_color=_MUTED,
    block_title_text_color=_TEXT,
    block_info_text_color=_MUTED,
    body_text_color=_TEXT,
    body_text_color_subdued=_MUTED,
    border_color_primary=_LINE,
    border_color_accent=_NEON,
    color_accent=_NEON,
    color_accent_soft="rgba(255, 79, 139, 0.16)",
    input_background_fill=_PANEL_2,
    input_background_fill_focus=_PANEL_2,
    input_border_color=_LINE,
    input_border_color_focus=_NEON,
    input_placeholder_color="#6f6886",
    checkbox_background_color=_PANEL_2,
    checkbox_border_color=_LINE,
    checkbox_background_color_selected=_NEON,
    checkbox_border_color_selected=_NEON,
    checkbox_label_background_fill=_PANEL_2,
    checkbox_label_background_fill_selected="rgba(255, 79, 139, 0.16)",
    checkbox_label_border_color=_LINE,
    checkbox_label_border_color_selected=_NEON,
    checkbox_label_text_color=_TEXT,
    checkbox_label_text_color_selected=_TEXT,
    button_primary_background_fill=_PRIMARY,
    button_primary_background_fill_hover=_PRIMARY_HOVER,
    button_primary_text_color="#ffffff",
    button_primary_border_color=_PRIMARY,
    button_secondary_background_fill=_PANEL_2,
    button_secondary_background_fill_hover="#2a2539",
    button_secondary_text_color=_TEXT,
    button_secondary_border_color=_LINE,
    button_cancel_background_fill="#3a1521",
    button_cancel_background_fill_hover="#4d1a2b",
    button_cancel_text_color="#ff9db8",
    button_cancel_border_color="#5c2233",
    slider_color=_NEON,
    table_even_background_fill=_PANEL,
    table_odd_background_fill=_PANEL_2,
    table_border_color=_LINE,
    table_row_focus="rgba(255, 79, 139, 0.12)",
    link_text_color=_CYAN,
    code_background_fill=_PANEL_2,
    panel_background_fill=_PANEL,
    panel_border_color=_LINE,
    shadow_drop="0 8px 24px rgba(0, 0, 0, 0.35)",
)

theme = gr.themes.Base(
    primary_hue=gr.themes.colors.pink,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)
_DARK_KEYS = set(inspect.signature(theme.set).parameters)
theme = theme.set(**_THEME_VALUES, **{f"{k}_dark": v for k, v in _THEME_VALUES.items()
                                       if f"{k}_dark" in _DARK_KEYS})

_UI_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@500&display=swap');
/* Only the page canvas is opaque, so the fixed glow layers below show through. */
body { background: #0c0a12 !important; }
gradio-app { background: transparent !important; }

/* ---- scroll-driven background: one glow layer per section, cross-faded ---- */
.jk-bg { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; }
.jk-bg-layer { position: absolute; inset: -15%; opacity: 0;
  transition: opacity 1.2s ease;
  transform: translate3d(0, calc(var(--jk-p, 0) * -80px), 0);
  animation: jk-drift 26s ease-in-out infinite alternate; }
.jk-bg-layer.on { opacity: 1; }
.jk-bg-layer[data-sec=top] { background:
  radial-gradient(42% 38% at 22% 12%, rgba(255, 79, 139, 0.20), transparent 70%),
  radial-gradient(38% 34% at 82% 8%, rgba(79, 227, 255, 0.12), transparent 70%); }
.jk-bg-layer[data-sec=studio] { background:
  radial-gradient(44% 40% at 18% 30%, rgba(255, 122, 89, 0.18), transparent 70%),
  radial-gradient(40% 36% at 85% 60%, rgba(255, 181, 71, 0.12), transparent 70%); }
.jk-bg-layer[data-sec=booth] { background:
  radial-gradient(46% 42% at 80% 25%, rgba(224, 48, 108, 0.24), transparent 70%),
  radial-gradient(42% 40% at 15% 70%, rgba(139, 92, 246, 0.18), transparent 70%); }
.jk-bg-layer[data-sec=library] { background:
  radial-gradient(44% 40% at 25% 35%, rgba(79, 227, 255, 0.15), transparent 70%),
  radial-gradient(40% 36% at 80% 75%, rgba(61, 220, 151, 0.11), transparent 70%); }
.jk-bg::after { content: ""; position: absolute; inset: -50%; opacity: 0.06; pointer-events: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
  animation: jk-grain 0.9s steps(5) infinite; }
@keyframes jk-grain { 0% { transform: translate(0, 0); } 20% { transform: translate(-3%, 2%); }
  40% { transform: translate(2%, -3%); } 60% { transform: translate(-2%, -1%); } 80% { transform: translate(3%, 3%); } }
@keyframes jk-drift { from { background-position: 0 0; translate: 0 0; } to { translate: 3% 2%; } }
html.jk-playing .jk-bg { animation: jk-breathe 3.2s ease-in-out infinite; }
@keyframes jk-breathe { 50% { opacity: 0.7; } }

/* ---- reveal on scroll (class added by _HEAD_JS only when motion is allowed) ---- */
html.jk-anim .jk-panel, html.jk-anim .jk-section { opacity: 0; transform: translateY(18px);
  transition: opacity 0.6s ease, transform 0.6s cubic-bezier(.2, .8, .2, 1); }
html.jk-anim .jk-panel.jk-in, html.jk-anim .jk-section.jk-in { opacity: 1; transform: none; }

/* ---- "Playing" badge in the nav ---- */
.jk-nav-live { display: none; align-items: center; gap: 8px; font-size: 12px; font-weight: 700;
  letter-spacing: 1.6px; text-transform: uppercase; color: #ff4f8b; }
.jk-nav-live b { display: inline-flex; align-items: flex-end; gap: 2px; height: 12px; }
.jk-nav-live i { width: 3px; height: 100%; background: #ff4f8b; border-radius: 1px;
  transform-origin: bottom; animation: jk-eq 0.7s ease-in-out infinite alternate; }
.jk-nav-live i:nth-child(2) { animation-delay: 0.2s; }
.jk-nav-live i:nth-child(3) { animation-delay: 0.4s; }
/* !important: Gradio also emits container-prefixed copies of the base rules,
   which outrank these html.jk-playing selectors. */
html.jk-playing .jk-nav-live { display: inline-flex !important; }
html.jk-playing .jk-record { animation-duration: 1.8s !important; }
html.jk-playing .jk-arm { transform: rotate(-4deg) !important; }
@keyframes jk-eq { from { transform: scaleY(0.25); } to { transform: scaleY(1); } }
html.jk-playing .jk-onair::before { animation-duration: 0.8s !important; }
.gradio-container { width: 100% !important; min-width: 0 !important; box-sizing: border-box;
  max-width: 1200px !important; margin: 0 auto !important;
  padding: 0 clamp(4px, 1.6vw, 20px) 40px !important;
  background: transparent !important; }
.gradio-container .row, .gradio-container .row > *, .gradio-container .block {
  min-width: 0 !important; max-width: 100%; box-sizing: border-box; }
.gradio-container .row { flex-wrap: wrap !important; }
.gradio-container .table-wrap { overflow-x: auto; max-width: 100%; }
footer { color: #6f6886 !important; }
button.primary, button.secondary, button.stop { border-radius: 999px !important; }

html { scroll-behavior: smooth; scroll-padding-top: 76px; }
/* Gradio's page gutter is 32px; shrink it on phones (clamp, since @media rules get
   container-prefixed and can't reach this element). */
main.fillable { padding-left: clamp(6px, 3vw, 32px) !important; padding-right: clamp(6px, 3vw, 32px) !important; }

/* ---- fixed nav (fixed, not sticky: .gradio-container clips overflow) ---- */
.jk-nav { position: fixed; top: 0; left: 0; right: 0; z-index: 50; height: 56px;
  display: flex; align-items: center; justify-content: space-between; padding: 0 24px;
  background: rgba(12, 10, 18, 0.72); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid #2e2942; }
.jk-nav-brand { font-family: 'Instrument Serif', Georgia, serif; font-style: italic; font-size: 24px;
  color: #f2eefa; text-decoration: none; letter-spacing: 0.2px; display: inline-flex; align-items: center; gap: 10px; }
.jk-nav-brand::before { content: ""; width: 14px; height: 14px; border-radius: 50%;
  background: radial-gradient(circle, #ff4f8b 0 22%, #0c0a12 24% 30%, #2a2438 32%);
  box-shadow: 0 0 0 1px #3a3350; }
.jk-nav::after { content: ""; position: absolute; left: 0; bottom: -1px; height: 2px;
  width: calc(var(--jk-p, 0) * 100%); background: linear-gradient(90deg, #ff4f8b, #ffb547);
  transition: width 0.1s linear; }
.jk-nav-links { display: flex; gap: 2px; }
.jk-nav-links a { position: relative; color: #a69fbc; text-decoration: none; font-weight: 500; font-size: 14px;
  padding: 6px 14px; transition: color 0.2s ease; }
.jk-nav-links a::after { content: ""; position: absolute; left: 14px; right: 14px; bottom: 2px; height: 1px;
  background: #ff4f8b; transform: scaleX(0); transform-origin: left; transition: transform 0.35s cubic-bezier(.2, .8, .2, 1); }
.jk-nav-links a:hover, .jk-nav-links a.active { color: #f2eefa; }
.jk-nav-links a:hover::after, .jk-nav-links a.active::after { transform: scaleX(1); }

/* ---- panels ---- */
.gradio-container .block { border-radius: 14px !important; }
.jk-panel { background: rgba(22, 19, 31, 0.86) !important; border: 1px solid #2a2539 !important;
  border-radius: 18px !important; padding: 22px !important; gap: 14px !important;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.03) inset, 0 20px 40px rgba(0, 0, 0, 0.3); }
.jk-panel .block { box-shadow: none !important; }
.jk-sub { font-size: 13px; font-weight: 600; color: #a69fbc; margin: 2px 2px 0; }

/* ---- hero: big serif type on the left, a turntable on the right ---- */
.jk-hero { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); align-items: center;
  gap: 48px; padding: 120px 0 56px; }
.jk-hero-title { font-family: 'Instrument Serif', Georgia, serif; font-weight: 400; font-size: 104px;
  line-height: 0.9; letter-spacing: -2px; color: #f2eefa; margin: 0 0 22px; }
.jk-hero-title em { color: #ff4f8b; font-style: italic; }
.jk-word { display: inline-block; animation: jk-rise 0.9s cubic-bezier(.2, .8, .2, 1) both; }
@keyframes jk-rise { from { opacity: 0; transform: translateY(0.35em) rotate(2deg); } to { opacity: 1; transform: none; } }
.jk-hero-sub { color: #c9c2dc; font-size: 19px; line-height: 1.5; max-width: 30ch;
  animation: jk-rise 0.9s 0.25s cubic-bezier(.2, .8, .2, 1) both; }
.jk-hero-cta { display: flex; align-items: center; gap: 12px; margin-top: 28px; flex-wrap: wrap;
  animation: jk-rise 0.9s 0.4s cubic-bezier(.2, .8, .2, 1) both; }
.jk-btn-primary, .jk-btn-ghost { display: inline-flex; align-items: center; gap: 10px; height: 48px;
  padding: 0 24px; border-radius: 999px; font-weight: 600; font-size: 15px; text-decoration: none;
  transition: transform 0.25s cubic-bezier(.2, .8, .2, 1), box-shadow 0.25s ease, border-color 0.25s ease, color 0.25s ease; }
.jk-btn-primary { color: #ffffff !important; background: #e0306c; }
.jk-btn-primary:hover { box-shadow: 0 12px 34px rgba(224, 48, 108, 0.45); }
.jk-btn-ghost { color: #f2eefa !important; border: 1px solid #3a3350; }
.jk-btn-ghost:hover { border-color: #f2eefa; }
.jk-meta { margin-top: 34px; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px;
  color: #8b84a1; letter-spacing: 0.4px; animation: jk-rise 0.9s 0.55s cubic-bezier(.2, .8, .2, 1) both; }
.jk-meta b { color: #ffb547; font-weight: 500; }

.jk-turntable { position: relative; width: min(400px, 100%); aspect-ratio: 1; justify-self: center;
  animation: jk-rise 1.1s 0.2s cubic-bezier(.2, .8, .2, 1) both; }
.jk-platter { position: absolute; inset: 0; border-radius: 50%;
  box-shadow: 0 30px 60px rgba(0, 0, 0, 0.55), 0 0 0 10px #15121c, 0 0 0 11px #2a2539; }
.jk-record { position: absolute; inset: 0; border-radius: 50%;
  background:
    conic-gradient(from 30deg, rgba(255, 255, 255, 0) 0deg, rgba(255, 255, 255, 0.07) 30deg,
      rgba(255, 255, 255, 0) 70deg, rgba(255, 255, 255, 0) 180deg, rgba(255, 255, 255, 0.05) 215deg,
      rgba(255, 255, 255, 0) 250deg),
    repeating-radial-gradient(circle, #121016 0 1.5px, #1a1721 1.5px 3px);
  animation: jk-spin 12s linear infinite; }
.jk-label { position: absolute; inset: 32%; border-radius: 50%; background-size: cover; background-position: center;
  box-shadow: 0 0 0 4px #0c0a12, 0 0 0 5px rgba(255, 255, 255, 0.08); }
.jk-label::after { content: ""; position: absolute; left: 50%; top: 50%; width: 9%; height: 9%;
  transform: translate(-50%, -50%); border-radius: 50%; background: #0c0a12; box-shadow: 0 0 0 2px #2a2539; }
@keyframes jk-spin { to { transform: rotate(360deg); } }
.jk-arm { position: absolute; top: -6%; right: -4%; width: 18%; height: 74%; transform-origin: 50% 9%;
  transform: rotate(-26deg); transition: transform 1.4s cubic-bezier(.3, .9, .3, 1); pointer-events: none; }
.jk-arm-base { position: absolute; top: 0; left: 50%; width: 64%; aspect-ratio: 1; transform: translateX(-50%);
  border-radius: 50%; background: radial-gradient(circle at 40% 35%, #4a4260, #1c1826 70%);
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.5); }
.jk-arm-rod { position: absolute; top: 9%; left: 50%; width: 5px; height: 84%; transform: translateX(-50%);
  border-radius: 3px; background: linear-gradient(90deg, #8d86a3, #d9d4e6 45%, #6f6886); }
.jk-arm-head { position: absolute; bottom: 0; left: 50%; width: 28%; height: 14%; transform: translateX(-50%) rotate(14deg);
  border-radius: 3px; background: linear-gradient(#d9d4e6, #8d86a3); }

/* ---- ticker: the library scrolls past like a station marquee ---- */
.jk-ticker { position: relative; overflow: hidden; border-top: 1px solid #2a2539; border-bottom: 1px solid #2a2539;
  padding: 16px 0; margin: 0 0 8px; -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent); }
.jk-ticker-track { display: flex; width: max-content; gap: 48px; animation: jk-marquee 38s linear infinite; }
.jk-ticker:hover .jk-ticker-track { animation-play-state: paused; }
.jk-tick { display: inline-flex; align-items: baseline; gap: 12px; white-space: nowrap; }
.jk-tick b { font-family: 'Instrument Serif', Georgia, serif; font-style: italic; font-weight: 400; font-size: 26px; color: #f2eefa; }
.jk-tick span { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; color: #8b84a1; }
.jk-tick i { color: #ff4f8b; font-style: normal; font-size: 14px; }
@keyframes jk-marquee { to { transform: translateX(-50%); } }

/* ---- section headers: mono index, serif title ---- */
.jk-section { display: grid; grid-template-columns: auto minmax(0, 1fr); column-gap: 20px; align-items: baseline;
  margin: 84px 0 22px; }
.jk-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; color: #ff4f8b; }
.jk-section-title { font-family: 'Instrument Serif', Georgia, serif; font-size: 52px; font-weight: 400;
  line-height: 1; color: #f2eefa; letter-spacing: -0.8px; }
.jk-section-desc { grid-column: 2; color: #a69fbc; font-size: 15px; margin-top: 8px; }

/* ---- buttons: deep pink fill keeps white text readable; neon is only the glow ---- */
button.primary { background: #e0306c !important;
  color: #ffffff !important; border: none !important; font-weight: 700 !important;
  box-shadow: none;
  transition: transform 0.18s cubic-bezier(.2, .8, .2, 1), box-shadow 0.18s ease; }
button.primary:hover { transform: translateY(-1px);
  box-shadow: 0 0 0 1px rgba(255, 79, 139, 0.25), 0 12px 40px rgba(255, 79, 139, 0.32); }
button.primary:disabled { opacity: 0.6; transform: none; box-shadow: none; cursor: progress; }
:focus-visible { outline: 2px solid #ff4f8b !important; outline-offset: 2px; }
.jk-surprise { background: transparent !important; color: #ffb547 !important;
  border: 1px solid rgba(255, 181, 71, 0.6) !important; font-weight: 700 !important; }
.jk-surprise:hover { background: rgba(255, 181, 71, 0.1) !important; }
.jk-shuffle:hover { border-color: #4fe3ff !important; color: #4fe3ff !important; }

/* ---- now playing ---- */
.jk-stage { background: linear-gradient(180deg, #1b1626, #13101b) !important;
  border: 1px solid rgba(255, 79, 139, 0.35) !important;
  box-shadow: 0 0 0 1px rgba(255, 79, 139, 0.08), 0 20px 50px rgba(255, 79, 139, 0.12); }
.jk-onair { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700;
  letter-spacing: 2px; text-transform: uppercase; color: #ff4f8b; }
.jk-onair::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: #ff4f8b;
  box-shadow: 0 0 10px #ff4f8b; animation: jk-blink 1.6s ease-in-out infinite; }
@keyframes jk-blink { 50% { opacity: 0.25; } }
.jk-viz { display: flex; align-items: center; gap: 16px; background: #0f0d16;
  border: 1px solid #2e2942; border-radius: 14px; padding: 12px 14px; }
.jk-viz-wave { flex: 1; min-width: 0; }
.jk-viz-btns { display: flex; flex-direction: column; gap: 8px; }
.jk-viz-hint { color: #8b84a1; font-size: 13px; }
.jk-skip { border-radius: 999px; border: 1px solid #2e2942; background: #1f1b2b; color: #f2eefa;
  padding: 7px 18px; cursor: pointer; font-size: 14px; font-weight: 600; white-space: nowrap; }
.jk-skip:hover { border-color: #4fe3ff; color: #4fe3ff; }
.jk-cues ul { list-style: none; padding-left: 0 !important; margin: 0; }
.jk-cues li { padding: 6px 0; border-bottom: 1px dashed #2e2942; }
.jk-cues code { background: rgba(79, 227, 255, 0.12) !important; color: #4fe3ff !important;
  border-radius: 6px; padding: 1px 6px; }

/* ---- studio: describe box, mood chips, segmented controls ---- */
.jk-studio { gap: 18px !important; }
.jk-studio .form { border: none !important; background: transparent !important;
  box-shadow: none !important; gap: 18px !important; }
.jk-studio .form > .block { background: transparent !important; border: none !important;
  padding: 0 !important; }
.jk-describe textarea { font-size: 17px !important; line-height: 1.55 !important;
  padding: 14px 16px !important; border-radius: 14px !important; min-height: 92px; }
.jk-describe label > span, .jk-chipset > span, .jk-seg > span { font-size: 13px !important;
  color: #a69fbc !important; font-weight: 600 !important; }
.jk-chipset .wrap, .jk-seg .wrap { gap: 8px !important; }
.jk-chipset label { border-radius: 999px !important; padding: 7px 14px !important;
  border: 1px solid #2e2942 !important; background: transparent !important;
  transition: all 0.15s ease; cursor: pointer; }
.jk-chipset label:hover { border-color: #4a4263 !important; }
.jk-chipset label.selected { background: rgba(255, 79, 139, 0.14) !important;
  border-color: rgba(255, 79, 139, 0.65) !important; color: #ffd6e5 !important; }
.jk-chipset input[type=checkbox], .jk-seg input[type=radio] { display: none !important; }
.jk-seg .wrap { display: inline-flex !important; gap: 0 !important; padding: 3px !important;
  border: 1px solid #2e2942; border-radius: 12px; background: #1f1b2b; flex-wrap: nowrap !important; }
.jk-seg label { border: none !important; background: transparent !important; border-radius: 9px !important;
  padding: 7px 14px !important; margin: 0 !important; cursor: pointer; color: #a69fbc !important;
  transition: all 0.15s ease; white-space: nowrap; }
.jk-seg label.selected { background: #2b2540 !important; color: #f2eefa !important;
  box-shadow: inset 0 0 0 1px rgba(255, 79, 139, 0.45); }
.jk-controls { align-items: flex-end !important; gap: 16px !important; }
.jk-seg { display: flex !important; flex-direction: column !important; align-items: flex-start !important; }
.jk-seg > span { display: block !important; margin-bottom: 6px !important; }
.jk-more { border-radius: 14px !important; }
.jk-hidden { display: none !important; }

/* ---- studio: latest-tracks grid with a live status card ---- */
.jk-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-top: 10px; }
.jk-card { display: block; text-align: left; background: transparent; border: none; padding: 0;
  color: inherit; cursor: pointer; font: inherit; min-width: 0; }
.jk-card-art { position: relative; aspect-ratio: 1 / 1; border-radius: 14px; overflow: hidden;
  background: #1f1b2b; border: 1px solid #2e2942; display: flex; align-items: center;
  justify-content: center; transition: transform 0.2s cubic-bezier(.2, .8, .2, 1), box-shadow 0.2s ease; }
.jk-card-art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.jk-card:hover .jk-card-art { transform: translateY(-2px);
  box-shadow: 0 0 0 1px rgba(255, 79, 139, 0.3), 0 12px 32px rgba(255, 79, 139, 0.22); }
.jk-card-art.jk-tilting { transition: transform 0.08s linear, box-shadow 0.2s ease; }
.jk-card-art::before { content: ""; position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: radial-gradient(circle at var(--gx, 50%) var(--gy, 50%), rgba(255, 255, 255, 0.22), transparent 55%);
  opacity: 0; transition: opacity 0.25s ease; }
.jk-card-art.jk-tilting::before { opacity: 1; }
.jk-card-play { position: absolute; right: 10px; bottom: 10px; width: 38px; height: 38px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px;
  color: #fff; background: #e0306c; opacity: 0;
  transform: translateY(6px); transition: all 0.2s ease; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4); }
.jk-card:hover .jk-card-play, .jk-card:focus-visible .jk-card-play { opacity: 1; transform: none; }
.jk-card-title { margin-top: 8px; font-weight: 600; font-size: 14px; color: #f2eefa;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.jk-card-meta { font-size: 12.5px; color: #a69fbc; margin-top: 2px; }
.jk-card-noart { font-size: 30px; color: #6f6886; }
.jk-card-pending { cursor: default; }
.jk-card-pending .jk-card-art { border: 1px dashed rgba(255, 79, 139, 0.55);
  background: linear-gradient(110deg, #1b1726 30%, #262036 50%, #1b1726 70%);
  background-size: 200% 100%; animation: jk-shimmer 1.6s linear infinite; }
.jk-card-pending .jk-card-meta { color: #ffb547; }
.jk-spinner { width: 34px; height: 34px; border-radius: 50%; border: 3px solid rgba(255, 79, 139, 0.25);
  border-top-color: #ff4f8b; animation: jk-spin 0.9s linear infinite; }
@keyframes jk-shimmer { to { background-position: -200% 0; } }
.jk-card-bar { height: 3px; border-radius: 2px; background: #2e2942; margin-top: 8px; overflow: hidden; }
.jk-card-bar i { display: block; height: 100%; background: linear-gradient(90deg, #ff4f8b, #ffb547);
  transition: width 0.4s ease; }
.jk-card-error { cursor: default; }
.jk-card-error .jk-card-art { border-color: rgba(255, 107, 107, 0.6); color: #ff6b6b;
  font-size: 30px; font-weight: 700; }
.jk-card-error .jk-card-meta { color: #ff9d9d; }

/* ---- results + library covers ---- */
.jk-result { border-color: rgba(79, 227, 255, 0.35) !important; }
.jk-covers .thumbnail-item, .jk-covers .thumbnail-lg { border-radius: 14px !important;
  overflow: hidden; }
.jk-covers .grid-wrap { padding: 4px !important; }
.jk-covers .caption-label { background: rgba(12, 10, 18, 0.82) !important; color: #f2eefa !important;
  font-weight: 600; border-radius: 8px; }
.jk-covers .grid-wrap.fixed-height { height: auto !important; min-height: 0 !important;
  max-height: none !important; }
.jk-covers .thumbnail-item { aspect-ratio: 1 / 1;
  transition: transform 0.2s cubic-bezier(.2, .8, .2, 1), box-shadow 0.2s ease; }
.jk-covers .thumbnail-item:hover { transform: translateY(-2px);
  box-shadow: 0 0 0 1px rgba(255, 79, 139, 0.3), 0 12px 32px rgba(255, 79, 139, 0.25); }
.jk-hint { color: #a69fbc; font-size: 13px; padding: 0 4px; }
.jk-create-report pre, .jk-create-report code { white-space: pre-wrap; }

/* ---- library table: square-ish corners so the rounded edge never clips text ---- */
.jk-panel .table-container, .jk-panel .table-wrap { border-radius: 10px !important; }
.jk-panel table td, .jk-panel table th { font-family: 'Inter', ui-sans-serif, sans-serif !important;
  padding: 8px 12px !important; }
.jk-panel table th { color: #a69fbc !important; font-weight: 700 !important; }

@media (prefers-reduced-motion: reduce) {
  .jk-record, .jk-word, .jk-hero-sub, .jk-hero-cta, .jk-meta, .jk-turntable, .jk-ticker-track,
  .jk-onair::before, .jk-card-pending .jk-card-art, .jk-bg, .jk-bg-layer, .jk-bg::after,
  .jk-nav-live i { animation: none !important; }
  .jk-bg-layer { transition: none; transform: none; }
  html { scroll-behavior: auto; }
}

/* Gradio prefixes rules inside @media with the container, so these start at .row/.jk-* */
@media (max-width: 640px) {
  .row > * { flex: 1 1 100% !important; width: 100% !important; }
  .jk-panel { padding: 14px !important; border-radius: 16px !important; }
  .jk-nav { justify-content: center; padding: 0 12px; }
  .jk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .jk-controls .form { flex-wrap: wrap !important; }
  .jk-controls .form > * { flex: 1 1 100% !important; min-width: 100% !important; }
  .jk-seg { overflow: visible !important; }
  .jk-seg .wrap { display: flex !important; width: 100%; box-sizing: border-box; }
  .jk-seg label { flex: 1 1 0; justify-content: center; padding: 7px 4px !important; }
  .jk-nav-brand, .jk-nav-live { display: none !important; }

  .jk-hero { grid-template-columns: 1fr; gap: 28px; padding-top: 88px; }
  .jk-turntable { width: min(260px, 80%); }
  .jk-section { margin-top: 56px; }
  .jk-section-title { font-size: 38px; }
  .jk-hero-title { font-size: 64px; letter-spacing: -1px; }
  .jk-tick b { font-size: 20px; }
  .jk-viz { flex-direction: column; align-items: stretch; }
  .jk-viz-btns { flex-direction: row; }
}
"""


# Fixed background: one glow layer per section, cross-faded by _HEAD_JS as you
# scroll (hero = pink/cyan, studio = warm, DJ booth = on-air magenta/violet,
# library = cool cyan/teal).
_BG_HTML = (
    "<div class='jk-bg' aria-hidden='true'>"
    + "".join(f"<div class='jk-bg-layer{' on' if s == 'top' else ''}' data-sec='{s}'></div>"
              for s in ("top", "studio", "booth", "library"))
    + "</div>"
)

_NAV_HTML = _BG_HTML + (
    "<nav class='jk-nav' aria-label='Sections'>"
    "<a class='jk-nav-brand' href='#top'>AI Jukebox</a>"
    "<span class='jk-nav-live' aria-live='polite'><b><i></i><i></i><i></i></b>Playing</span>"
    "<div class='jk-nav-links'>"
    "<a href='#studio' data-sec='studio'>Studio</a>"
    "<a href='#booth' data-sec='booth'>DJ Booth</a>"
    "<a href='#library' data-sec='library'>Library</a>"
    "</div></nav>"
)

# Highlights the nav link for the section in view: the last section whose
# header has passed 40% of the viewport. Gradio injects this script after the
# page's load event, so it runs immediately rather than waiting for "load".
_HEAD_JS = """
<script>
(function () {
  var ids = ['studio', 'booth', 'library'];
  function update() {
    var current = null;
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.getBoundingClientRect().top < window.innerHeight * 0.4) current = id;
    });
    document.querySelectorAll('.jk-nav a[data-sec]').forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('data-sec') === current);
    });
    // Background mood follows the section; --jk-p (0..1) drives a slow parallax drift.
    var bgSec = current || 'top';
    document.querySelectorAll('.jk-bg-layer').forEach(function (l) {
      l.classList.toggle('on', l.getAttribute('data-sec') === bgSec);
    });
    var room = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    document.documentElement.style.setProperty('--jk-p', (window.scrollY / room).toFixed(3));
  }
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  setTimeout(update, 500);

  // Panels and section headers rise in as they enter the viewport. Skipped
  // entirely for reduced-motion users, so nothing is ever hidden for them.
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.classList.add('jk-anim');
    var reveal = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('jk-in'); reveal.unobserve(e.target); }
      });
    }, { threshold: 0.06 });
    var watch = function () {
      document.querySelectorAll('.jk-panel, .jk-section').forEach(function (el) {
        if (!el.dataset.jkReveal) { el.dataset.jkReveal = '1'; reveal.observe(el); }
      });
    };
    setTimeout(watch, 200);
    setInterval(watch, 2000);
  }

  // Music-reactive: while any player is playing, the record spins up, the
  // equalizers dance, the background breathes and the nav shows "Playing".
  // Gradio's players can sit inside shadow roots, so look there too.
  function anyPlaying(root) {
    var list = root.querySelectorAll('audio');
    for (var i = 0; i < list.length; i++) if (!list[i].paused && !list[i].ended) return true;
    var nodes = root.querySelectorAll('*');
    for (var j = 0; j < nodes.length; j++) {
      if (nodes[j].shadowRoot && anyPlaying(nodes[j].shadowRoot)) return true;
    }
    return false;
  }
  // Pointer motion (skipped for reduced motion): track cards tilt toward the
  // cursor with a soft glare, and the hero buttons lean toward it. Delegated
  // on document because the card grid is re-rendered after every generation.
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.addEventListener('pointermove', function (e) {
      var t = e.target.closest ? e.target : null;
      var art = t && t.closest('.jk-card:not(.jk-card-pending):not(.jk-card-error) .jk-card-art');
      document.querySelectorAll('.jk-card-art.jk-tilting').forEach(function (a) {
        if (a !== art) { a.classList.remove('jk-tilting'); a.style.transform = ''; }
      });
      if (art) {
        var r = art.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
        art.classList.add('jk-tilting');
        art.style.transform = 'perspective(700px) rotateY(' + (x * 14).toFixed(2) + 'deg) rotateX(' +
          (-y * 14).toFixed(2) + 'deg) translateY(-3px)';
        art.style.setProperty('--gx', ((x + 0.5) * 100).toFixed(1) + '%');
        art.style.setProperty('--gy', ((y + 0.5) * 100).toFixed(1) + '%');
      }
      document.querySelectorAll('.jk-hero-cta a').forEach(function (b) {
        var br = b.getBoundingClientRect();
        var dx = e.clientX - (br.left + br.width / 2), dy = e.clientY - (br.top + br.height / 2);
        var near = Math.abs(dx) < br.width && Math.abs(dy) < br.height * 1.6;
        b.style.transform = near ? 'translate(' + (dx * 0.12).toFixed(1) + 'px,' + (dy * 0.2).toFixed(1) + 'px)' : '';
      });
    }, { passive: true });
  }

  setInterval(function () {
    // Gradio's waveform player may keep its <audio> off the page; its button
    // reads "Pause" while playing, so that counts too.
    var gradioPlaying = !!document.querySelector('.play-pause-button[aria-label="Pause"]');
    document.documentElement.classList.toggle('jk-playing', gradioPlaying || anyPlaying(document));
  }, 700);

  // Studio card click: hand the song id to a hidden Gradio textbox, whose
  // change event loads the track. The timestamp makes repeat clicks register.
  window.jkPick = function (id) {
    var box = document.querySelector('#jk-pick textarea, #jk-pick input');
    if (!box) return;
    box.value = id + '|' + Date.now();
    box.dispatchEvent(new Event('input', { bubbles: true }));
    var player = document.getElementById('studio-player');
    if (player) player.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
})();
</script>
"""


def _hero_html() -> str:
    """Editorial hero: serif headline on the left, a turntable on the right whose
    label is the newest track's cover. The record spins up and the tonearm drops
    while anything is playing (see html.jk-playing in _UI_CSS)."""
    songs = library.all()
    label = _thumb_uri(songs[0].cover_path) if songs else ""
    label_style = f" style=\"background-image:url('{label}')\"" if label else ""
    vocal = sum(1 for s in songs if s.vocal)
    return (
        "<div class='jk-hero'>"
        "<div class='jk-hero-text'>"
        "<h1 class='jk-hero-title'><span class='jk-word'>AI</span> "
        "<em class='jk-word' style='animation-delay:.12s'>Jukebox</em></h1>"
        "<p class='jk-hero-sub'>Describe a feeling. We write the song, paint the sleeve, "
        "and put a DJ on the mic.</p>"
        "<div class='jk-hero-cta'>"
        f"<a class='jk-btn-primary' href='#booth'>{_PLAY_SVG} Play the sample show</a>"
        "<a class='jk-btn-ghost' href='#studio'>Make a song</a>"
        "</div>"
        f"<div class='jk-meta'>Side A · <b>{len(songs)} tracks</b> in the crate · "
        f"{vocal} vocal, {len(songs) - vocal} instrumental · Boulder, CO</div>"
        "</div>"
        "<div class='jk-turntable' aria-hidden='true'>"
        "<div class='jk-platter'></div>"
        f"<div class='jk-record'><div class='jk-label'{label_style}></div></div>"
        "<div class='jk-arm'><div class='jk-arm-rod'></div><div class='jk-arm-base'></div>"
        "<div class='jk-arm-head'></div></div>"
        "</div></div>"
    )


def _ticker_html() -> str:
    """Station marquee of every track in the library (duplicated for a seamless loop)."""
    items = "".join(
        f"<span class='jk-tick'><i>✦</i><b>{escape(s.title)}</b><span>{escape(s.genre)}</span></span>"
        for s in library.all()
    ) or "<span class='jk-tick'><b>Your crate is empty</b></span>"
    return (f"<div class='jk-ticker' aria-label='Tracks in the library'>"
            f"<div class='jk-ticker-track'>{items}{items}</div></div>")


def _section(num: str, title: str, desc: str) -> str:
    return (
        "<div class='jk-section'>"
        f"<span class='jk-num'>{num}</span>"
        f"<div><div class='jk-section-title'>{title}</div>"
        f"<div class='jk-section-desc'>{desc}</div></div>"
        "</div>"
    )


def _sub(text: str) -> str:
    return f"<div class='jk-sub'>{text}</div>"


_CREATE_LABEL = "Generate song"
_CREATE_BUSY = "Generating… this takes about a minute"
_BUILD_LABEL = "Build the show"
_BUILD_BUSY = "Building the show…"


with gr.Blocks(title="AI Jukebox", theme=theme, css=_UI_CSS, head=_HEAD_JS) as demo:
    gr.HTML(_NAV_HTML)
    gr.HTML(_hero_html(), elem_id="top")
    ticker = gr.HTML(_ticker_html())

    # ---------------- 1 · Studio: create a song ----------------
    gr.HTML(_section("01", "Studio", "Describe a song, pick a vibe, and we write, play and paint it."),
            elem_id="studio")
    with gr.Column(elem_classes=["jk-panel", "jk-studio"]):
        # The description is the song's theme: it feeds the lyrics, title and cover prompts.
        mood_custom = gr.Textbox(label="Describe your song", lines=3, max_lines=6,
                                 placeholder="A hopeful song about first light over the bay",
                                 elem_classes=["jk-describe"])
        mood_multi = gr.CheckboxGroup(label="Mood", choices=MOODS, value=["hopeful"],
                                      elem_classes=["jk-chipset"])
        with gr.Row(equal_height=False, elem_classes=["jk-controls"]):
            genre_choice = gr.Dropdown(label="Style", choices=GENRES, value="upbeat indie pop",
                                       scale=2, min_width=200)
            vocal_radio = gr.Radio(choices=["Vocal", "Instrumental"], value="Vocal",
                                   label="Track type", elem_classes=["jk-seg"], scale=2,
                                   min_width=220)
            duration_slider = gr.Radio(choices=[("15s", 15), ("20s", 20), ("30s", 30),
                                                ("45s", 45), ("60s", 60)],
                                       value=20, label="Length", elem_classes=["jk-seg"],
                                       scale=3, min_width=280)
        genre_custom = gr.Textbox(label="Custom style", placeholder="dreamy synthwave ballad",
                                  visible=False)
        with gr.Accordion("More options", open=False, elem_classes=["jk-more"]):
            with gr.Row():
                title_box = gr.Textbox(label="Title", placeholder="Leave blank and we'll name it")
                vocal_style = gr.Dropdown(label="Vocal style", choices=VOCAL_STYLES, value="Auto")
            with gr.Row():
                energy_slider = gr.Slider(1, 10, value=5, step=1,
                                          label="Energy (1 = calm, 10 = intense)")
                bpm_slider = gr.Slider(0, 220, value=0, step=2, label="Tempo (BPM, 0 = auto)")
            with gr.Row():
                key_choice = gr.Dropdown(label="Key", choices=KEYS, value="Auto")
                tsig_choice = gr.Dropdown(label="Time signature", choices=TIME_SIGNATURES,
                                          value="Auto")
            thinking_box = gr.Checkbox(label="Music planning (may take longer)", value=False)
            lyrics_box = gr.Textbox(lines=5, placeholder="[Verse 1]\n…",
                                    label="Custom lyrics (vocal tracks; leave blank for AI-written)")
        with gr.Row():
            create_btn = gr.Button(_CREATE_LABEL, variant="primary", scale=3)
            surprise_btn = gr.Button("Surprise me", scale=1, elem_classes=["jk-surprise"])

        studio_grid = gr.HTML(_studio_grid_html())
        # Hidden bridge: a card click writes "<song id>|<time>" here (see jkPick in _HEAD_JS).
        studio_pick = gr.Textbox(elem_id="jk-pick", elem_classes=["jk-hidden"],
                                 show_label=False, container=False)
        song_audio = gr.Audio(label="Now previewing", type="filepath", elem_id="studio-player",
                              visible=False)
        with gr.Accordion("Lyrics and details for the newest song", open=False):
            with gr.Row(equal_height=False):
                cover_img = gr.Image(label="Cover art", type="filepath", height=240, scale=1,
                                     show_label=False)
                create_report = gr.Markdown("Generate a song to see its lyrics and production log.",
                                            elem_classes=["jk-create-report"])

    # ---------------- 2 · DJ Booth: queue + AI DJ ----------------
    gr.HTML(_section(
        "02", "DJ Booth",
        "Line up tracks and the AI DJ introduces each one. Everything plays as one "
        "continuous show, so speech never overlaps the music."
    ), elem_id="booth")
    with gr.Column(elem_classes=["jk-panel"]):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                gr.HTML(_sub("Setlist"))
                # Starts with the bundled samples queued, so one click builds a show.
                show_picker = gr.Dropdown(label="Queue (tracks play in the order you pick them)",
                                          multiselect=True, choices=_song_choices(),
                                          value=[sid for _, sid in _song_choices()][:3] or None)
                with gr.Row():
                    build_btn = gr.Button(_BUILD_LABEL, variant="primary", scale=2)
                    shuffle_btn = gr.Button("Shuffle", scale=1, elem_classes=["jk-shuffle"])
            with gr.Column(scale=2):
                gr.HTML(_sub("DJ voice"))
                voice_ref = gr.Audio(label="Voice reference (optional MP3/WAV; blank = default voice)",
                                     type="filepath", sources=["upload"])
    with gr.Column(elem_classes=["jk-panel", "jk-stage"]):
        gr.HTML("<div class='jk-onair'>On air</div>")
        show_covers = gr.Gallery(label="Tonight's set", columns=4, height=190, object_fit="cover",
                                 show_label=False, allow_preview=False,
                                 elem_classes=["jk-covers"], visible=False)
        show_audio = gr.Audio(label="Now playing (continuous mix)", type="filepath",
                              autoplay=True, elem_id="show-player")
        jukebox_viz = gr.HTML(_viz_html("", []))
        show_cue = gr.Markdown("Pick tracks in the setlist, then press **Build the show**.",
                               elem_classes=["jk-cues"])

    # ---------------- 3 · Library ----------------
    gr.HTML(_section("03", "Library", "Every track with its matching cover art."),
            elem_id="library")
    with gr.Column(elem_classes=["jk-panel"]):
        library_gallery = gr.Gallery(label="All tracks", columns=4, height="auto",
                                     object_fit="cover", show_label=False,
                                     elem_classes=["jk-covers"],
                                     value=_library_gallery_items())
        gr.HTML("<div class='jk-hint'>Click a cover to preview that track.</div>")
        preview_audio = gr.Audio(label="Preview", type="filepath", visible=False)
        library_table = gr.Dataframe(headers=LIBRARY_HEADERS, type="array",
                                     value=_library_rows(), interactive=False)
        with gr.Accordion("Manage tracks: rename, delete, refresh", open=False):
            with gr.Row():
                rename_picker = gr.Dropdown(label="Rename a track", choices=_song_choices())
                rename_box = gr.Textbox(label="New title", placeholder="What should we call it?")
                rename_btn = gr.Button("Rename")
            with gr.Row():
                delete_picker = gr.Dropdown(label="Delete a track", choices=_song_choices())
                delete_btn = gr.Button("Delete", variant="stop")
                refresh_btn = gr.Button("Refresh")

    gr.HTML("<div class='jk-section-desc' style='text-align:center;margin-top:28px'>"
            "Built with the class AI services · Boulder, Colorado</div>")

    # -- wiring ---------------------------------------------------------
    # Reveal the custom-genre box only when "Custom…" is chosen.
    genre_choice.change(
        lambda g: gr.update(visible=g == "Custom…"), inputs=genre_choice, outputs=genre_custom
    )
    # Vocals style is only meaningful for vocal tracks.
    vocal_radio.change(
        lambda v: gr.update(visible=v == "Vocal"),
        inputs=vocal_radio, outputs=vocal_style,
    )

    # Lock the button against double runs, then stream a live status card into the
    # track grid while the song is made. .then() runs after success and failure
    # alike, so the button always comes back.
    create_btn.click(
        lambda: gr.update(interactive=False, value=_CREATE_BUSY), outputs=create_btn,
    ).then(
        create_song_live,
        inputs=[title_box, genre_choice, genre_custom, mood_multi, mood_custom,
                vocal_radio, vocal_style, energy_slider, bpm_slider, key_choice,
                tsig_choice, lyrics_box, duration_slider, thinking_box, show_picker],
        outputs=[studio_grid, song_audio, cover_img, create_report, show_picker,
                 library_gallery, delete_picker, rename_picker, library_table],
        show_progress="hidden",
    ).then(
        lambda: (gr.update(interactive=True, value=_CREATE_LABEL), _ticker_html()),
        outputs=[create_btn, ticker],
    )
    studio_pick.change(play_pick, inputs=studio_pick, outputs=song_audio)

    build_btn.click(
        lambda: gr.update(interactive=False, value=_BUILD_BUSY), outputs=build_btn,
    ).then(
        build_show,
        inputs=[show_picker, voice_ref],
        outputs=[show_audio, show_covers, show_cue, jukebox_viz],
    ).then(
        lambda: gr.update(interactive=True, value=_BUILD_LABEL), outputs=build_btn,
    )

    # Click a library cover to hear that track on its own.
    library_gallery.select(preview_track, outputs=preview_audio)

    surprise_btn.click(
        surprise_me, inputs=[],
        outputs=[title_box, genre_choice, mood_multi, energy_slider, bpm_slider,
                 key_choice, tsig_choice, vocal_style, mood_custom, genre_custom],
    )
    shuffle_btn.click(shuffle_queue, inputs=[show_picker], outputs=[show_picker])
    rename_btn.click(
        rename_song, inputs=[rename_picker, rename_box, show_picker],
        outputs=[library_table, show_picker, delete_picker, rename_picker,
                 library_gallery, rename_box],
    ).then(lambda: (_studio_grid_html(), _ticker_html()), outputs=[studio_grid, ticker])

    delete_btn.click(delete_song, inputs=[delete_picker, show_picker],
                     outputs=[library_table, show_picker, delete_picker,
                              rename_picker, library_gallery],
                     ).then(lambda: (_studio_grid_html(), _ticker_html()), outputs=[studio_grid, ticker])
    refresh_btn.click(refresh_library, inputs=[show_picker],
                      outputs=[library_table, show_picker, delete_picker,
                               rename_picker, library_gallery],
                      ).then(lambda: (_studio_grid_html(), _ticker_html()), outputs=[studio_grid, ticker])


# Two jobs at a time is plenty for the shared class services.
demo.queue(default_concurrency_limit=2)

if __name__ == "__main__":
    demo.launch(
        show_api=False,
        server_name=os.environ.get("AIJ_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("AIJ_PORT", "7860")),
        share=os.environ.get("AIJ_SHARE", "0") == "1",
    )
