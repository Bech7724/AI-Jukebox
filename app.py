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
import os
import random
import time
from pathlib import Path

import gradio as gr

from ai_jukebox import dj, media, pipeline
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


def _library_gallery_items():
    return [(s.cover_path, f"{s.title} — {s.genre} ({_track_type(s)})")
            for s in library.all() if s.cover_path]


def _df_update() -> gr.Dataframe:
    return gr.Dataframe(value=_library_rows(), headers=LIBRARY_HEADERS, type="array")


def _dropdown_update() -> gr.Dropdown:
    return gr.Dropdown(choices=_song_choices(), value=None)


def _picker_update(value=None) -> gr.Dropdown:
    """Dropdown refresh that preserves a selectable value (queue order)."""
    return gr.Dropdown(choices=_song_choices(), value=value or None)


def _gallery_update(columns=3) -> gr.Gallery:
    return gr.Gallery(value=_library_gallery_items(), columns=columns, height=220)


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
    title = (title or "").strip() or "Untitled Song"
    genre = genre_choice if genre_choice and genre_choice != "Custom…" else (
        (genre_custom or "").strip() or "upbeat indie pop")
    mood_parts = [m for m in (mood_multi or []) if m]
    if (mood_custom or "").strip():
        mood_parts.append(mood_custom.strip())
    mood = ", ".join(mood_parts) or "hopeful and sunny"
    vocal = vocal_choice == "Vocal"
    progress(0.05, desc="Starting…")
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
    lines.append("\n_Track added to the library — queue it in section 2._")
    return (song.audio_path, song.cover_path, "\n".join(lines),
            _picker_update(value=library.prune_ids(queue)),
            _gallery_update(), _dropdown_update(), _dropdown_update())


# -------------------------------------------------------- section 2: queue + DJ

def _format_ts(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def build_show(selected_ids, voice_ref):
    songs = [s for s in library.all() if s.id in (selected_ids or [])]
    if not songs:
        return (None, gr.Gallery(value=[], columns=3, height=200),
                "⚠️ Pick at least one track, then press **Build the show**.",
                _viz_html("", []))
    # Preserve the order in which the user selected tracks (the queue order).
    order = {s.id: i for i, s in enumerate(songs)}
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
    lines = [f"🎙️ Show built — DJ voice: **{voice_note}**. Queue auto-advances; no overlap."]
    for seg, t in zip(segments, starts):
        prefix = "🎙️ DJ intro" if seg["kind"] == "intro" else f"🎵 {seg['label']}"
        lines.append(f"- `{_format_ts(t)}` {prefix}")
    gallery_items = [
        (s.cover_path, f"{s.title} — {s.genre} ({_track_type(s)})")
        for s in songs if s.cover_path
    ]
    viz = _viz_html(
        mixed,
        [(t, "DJ" if seg["kind"] == "intro" else seg["label"].split(" · ")[0])
         for seg, t in zip(segments, starts)],
    )
    return (
        mixed,
        gr.Gallery(value=gallery_items, columns=max(1, len(gallery_items)), height=200),
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

SURPRISE_TITLES = [
    "Midnight Mirage", "Canyon Echo", "Golden Hour Drive", "Starlit Campfire",
    "Pine & Rain", "High Country Haze", "Flatiron Funk", "Buffalo Moon",
    "Alpine Glow", "Skyline Serenade",
]


def surprise_me():
    """One click: random title + full styling so the DJ booth rolls its own."""
    moods = random.sample(MOODS, k=random.randint(1, 3))
    return (
        gr.update(value=random.choice(SURPRISE_TITLES)),
        gr.update(value=random.choice([g for g in GENRES if g != "Custom…"])),
        gr.update(value=moods),
        gr.update(value=random.randint(1, 10)),
        gr.update(value=random.choice([0, 80, 92, 104, 116, 128, 140, 152])),
        gr.update(value=random.choice(KEYS)),
        gr.update(value=random.choice(TIME_SIGNATURES)),
        gr.update(value=random.choice(VOCAL_STYLES)),
        gr.update(value=""),
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
_SKIP_JS = ("var a=document.querySelector('#show-player audio');"
            "var box=document.getElementById('jukebox-controls');"
            "if(!a||!box)return;"
            "var cs=(box.getAttribute('data-cues')||'').split(',').map(parseFloat)"
            ".filter(function(x){return isFinite(x)});"
            "var t=a.currentTime||0,n=-1,i;"
            "if(d>0){for(i=0;i<cs.length;i++){if(cs[i]>t+0.6){n=i;break}}}"
            "else{for(i=cs.length-1;i>=0;i--){if(cs[i]<t-1.0){n=i;break}}}"
            "if(n>=0){a.currentTime=cs[n];if(a.paused)a.play()}")

_BTN_TPL = (
    '<button onclick="(function(d){__SKIP__})(%d)" '
    'style="border-radius:999px;border:1px solid #e2dac6;background:#ffffff;'
    'color:#2e2a24;padding:7px 18px;cursor:pointer;font-size:14px;'
    'font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.06)">%s</button>'
)


def _viz_html(mix_path, markers):
    """Waveform of the mixed show + ⏮/⏭ skip buttons, as one HTML block."""
    if not mix_path or not markers:
        return (
            "<div id='jukebox-controls' data-cues=''>"
            "<div style='color:#8a8172;font-size:13px;padding:8px 2px'>"
            "🎼 Build a show to see its mix waveform — the ⏮ Prev / ⏭ Next "
            "buttons skip between tracks (or drag the player's seek bar)."
            "</div></div>"
        )
    cues = ",".join(f"{t:.2f}" for t, _ in markers)
    svg = media.waveform_svg(mix_path, markers=markers)
    prev = _BTN_TPL.replace("__SKIP__", _SKIP_JS) % (-1, "⏮ Prev")
    nxt = _BTN_TPL.replace("__SKIP__", _SKIP_JS) % (1, "⏭ Next")
    return (
        f"<div id='jukebox-controls' data-cues='{cues}'>"
        f"<div style='display:flex;align-items:center;gap:16px'>"
        f"<div style='flex:1;min-width:300px'>{svg}</div>"
        f"<div style='display:flex;flex-direction:column;gap:8px'>{prev}{nxt}</div>"
        f"</div></div>"
    )


# ---------------------------------------------------------------------- UI

# Flatirons Boulder theme: warm paper, terracotta rock, sand, sage — a light,
# high-contrast palette that is easy to read (no black-on-dark).
_PAPER = "#f5f1e8"            # warm, soft background
_CARD = "#ffffff"
_INK = "#2e2a24"              # warm near-black text
_MUTED = "#6e675a"
_TERRA = "#a6503c"            # flatiron red-rock (primary buttons/accents)
_TERRA_HOVER = "#8e4231"
_SAND = "#e2dac6"             # borders
_SKY = "#4a7b96"              # link / info blue (Boulder sky)

theme = gr.themes.Base(
    primary_hue=gr.themes.colors.orange,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    body_background_fill=_PAPER,
    body_background_fill_dark=_PAPER,
    background_fill_secondary=_PAPER,
    block_background_fill=_CARD,
    block_background_fill_dark=_CARD,
    block_border_color=_SAND,
    block_label_background_fill=_PAPER,
    block_label_text_color=_MUTED,
    block_title_text_color=_INK,
    body_text_color=_INK,
    input_background_fill=_CARD,
    input_border_color=_SAND,
    button_primary_background_fill=_TERRA,
    button_primary_background_fill_hover=_TERRA_HOVER,
    button_primary_text_color="#ffffff",
    button_primary_border_color=_TERRA,
    button_secondary_background_fill=_CARD,
    button_secondary_text_color=_INK,
    button_secondary_border_color=_SAND,
    slider_color=_TERRA,
    slider_color_dark=_TERRA,
    border_color_primary=_SAND,
    border_color_accent=_TERRA,
    link_text_color=_SKY,
    link_text_color_dark=_SKY,
    body_text_size="15px",
    input_text_size="15px",
    button_large_text_size="16px",
)

_UI_CSS = """
.gradio-container { max-width: 1180px !important; margin: 0 auto !important; }
button { border-radius: 999px !important; }
blockquote { border-left: 3px solid #a6503c !important; }
footer { color: #7a7264 !important; }

/* ---- hero header ---- */
.jk-hero { padding: 26px 4px 18px; border-bottom: 2px solid #e2dac6; margin-bottom: 18px; }
.jk-hero-title { font-size: 30px; font-weight: 800; letter-spacing: -0.4px; color: #2e2a24; }
.jk-hero-title .city { color: #8a8172; font-weight: 600; }
.jk-hero-sub { color: #6e675a; font-size: 14px; margin-top: 6px; max-width: 780px; line-height: 1.55; }
.jk-hero-chip { display: inline-block; margin-top: 10px; background: #f0e8d6; color: #7a5f2e;
  font-size: 12.5px; font-weight: 600; padding: 4px 12px; border-radius: 999px; border: 1px solid #e2dac6; }

/* ---- numbered section banners ---- */
.jk-section { display: flex; align-items: center; gap: 12px; margin: 26px 0 12px;
  padding-bottom: 10px; border-bottom: 1px solid #e2dac6; }
.jk-badge { flex: none; width: 34px; height: 34px; border-radius: 50%;
  background: #a6503c; color: #fff; font-weight: 800; font-size: 17px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 6px rgba(166, 80, 60, 0.35); }
.jk-section-title { font-size: 20px; font-weight: 800; color: #2e2a24; letter-spacing: -0.2px; }
.jk-section-desc { color: #7a7264; font-size: 13px; margin-top: 1px; }

/* ---- group mini-captions ---- */
.jk-group-cap { font-size: 13px; font-weight: 700; color: #a6503c; text-transform: uppercase;
  letter-spacing: 0.6px; margin-bottom: 2px; }

/* ---- hero actions ---- */
button.primary { font-size: 15px !important; font-weight: 700 !important; }
"""


def _hero_html() -> str:
    chip = ""
    if _seeded:
        chip = "<span class='jk-hero-chip'>▶ 3 sample tracks preloaded — play instantly</span>"
    return (
        "<div class='jk-hero'>"
        "<div class='jk-hero-title'>🏔️ AI Jukebox <span class='city'>· Boulder, Colorado</span></div>"
        "<div class='jk-hero-sub'>A Flatirons-inspired jukebox — rock, sand &amp; sky on one "
        "screen. Songs by ACE-Step (9007), covers by FLUX (9006), lyrics &amp; DJ scripts by "
        "Qwen (9001), DJ voice by Chatterbox (9008). Port 9000 is never used.</div>"
        + chip + "</div>"
    )


def _section(num: str, title: str, desc: str) -> str:
    return (
        "<div class='jk-section'>"
        f"<span class='jk-badge'>{num}</span>"
        f"<div><div class='jk-section-title'>{title}</div>"
        f"<div class='jk-section-desc'>{desc}</div></div>"
        "</div>"
    )

with gr.Blocks(title="AI Jukebox · Boulder", theme=theme, css=_UI_CSS) as demo:
    gr.HTML(_hero_html())

    # ---------------- 1 · Create a song ----------------
    gr.HTML(_section("1", "Create a song",
                     "Style, mood, energy, key & meter — vocal or instrumental"))
    with gr.Row(equal_height=False):
        with gr.Group():
            gr.Markdown("<div class='jk-group-cap'>Identity &amp; style</div>")
            title_box = gr.Textbox(label="Title", placeholder="Neon Afterglow")
            genre_choice = gr.Dropdown(label="Genre / style", choices=GENRES,
                                       value="upbeat indie pop", allow_custom_value=True)
            genre_custom = gr.Textbox(label="Custom genre…",
                                      placeholder="e.g. dreamy synthwave ballad",
                                      visible=False)
            mood_multi = gr.Dropdown(label="Mood / theme (pick any)", choices=MOODS,
                                     multiselect=True, value=["hopeful"])
            mood_custom = gr.Textbox(label="…or your own mood",
                                     placeholder="late-night drive through the city")
            vocal_style = gr.Dropdown(label="Vocals style (vocal tracks)",
                                      choices=VOCAL_STYLES, value="Auto")
        with gr.Group():
            gr.Markdown("<div class='jk-group-cap'>Sound &amp; meter</div>")
            vocal_radio = gr.Radio(choices=["Vocal", "Instrumental"], value="Vocal",
                                   label="Track type")
            duration_slider = gr.Slider(8, 60, value=20, step=2,
                                        label="Track length (seconds)")
            energy_slider = gr.Slider(1, 10, value=5, step=1,
                                      label="Energy (1 = whisper, 10 = fever)")
            bpm_slider = gr.Slider(0, 220, value=0, step=2, label="Tempo (BPM, 0 = auto)")
            key_choice = gr.Dropdown(label="Key", choices=KEYS, value="Auto")
            tsig_choice = gr.Dropdown(label="Time signature", choices=TIME_SIGNATURES,
                                      value="Auto")
    with gr.Row():
        create_btn = gr.Button("🎬 Generate song + cover", variant="primary", scale=3)
        surprise_btn = gr.Button("🎲 Surprise me", scale=1)
    with gr.Accordion("Custom lyrics (optional — vocal tracks; blank = AI-written)",
                      open=False):
        lyrics_box = gr.Textbox(lines=5, placeholder="[Verse 1]\n…", label="")
        thinking_box = gr.Checkbox(label="LM planning (slower, richer)", value=False)
    with gr.Row():
        song_audio = gr.Audio(label="Your song", type="filepath")
        cover_img = gr.Image(label="Cover art", type="filepath", height=300)
    create_report = gr.Markdown("")

    # ---------------- 2 · Playback queue with AI DJ ----------------
    gr.HTML(_section(
        "2", "Playback queue — AI DJ",
        "Pick tracks in order, optionally clone the DJ's voice, then Build the show. "
        "The show is mixed into one continuous track: the queue advances itself and "
        "speech never overlaps music."
    ))
    with gr.Group():
        gr.Markdown("<div class='jk-group-cap'>Setlist &amp; voice</div>")
        with gr.Row():
            show_picker = gr.Dropdown(label="Queue (pick tracks in order)", multiselect=True,
                                      choices=_song_choices())
            voice_ref = gr.Audio(label="DJ voice reference (optional MP3/WAV)",
                                 type="filepath")
        with gr.Row():
            build_btn = gr.Button("🎙️ Build the show", variant="primary", scale=2)
            shuffle_btn = gr.Button("🔀 Shuffle queue", scale=1)
    show_audio = gr.Audio(label="Queue player (continuous mix)", type="filepath",
                          autoplay=True, elem_id="show-player")
    jukebox_viz = gr.HTML(_viz_html("", []))
    with gr.Row():
        show_cue = gr.Markdown("Pick tracks above, then **Build the show**.")
        show_covers = gr.Gallery(label="Covers in this queue", columns=3, height=200)

    # ---------------- 3 · Library ----------------
    gr.HTML(_section("3", "Library", "Every track's title and matching cover art"))
    library_gallery = gr.Gallery(label="All tracks", columns=3, height=220,
                                 value=_library_gallery_items())
    library_table = gr.Dataframe(headers=LIBRARY_HEADERS, type="array",
                                 value=_library_rows())
    with gr.Row():
        rename_picker = gr.Dropdown(label="Rename a track", choices=_song_choices())
        rename_box = gr.Textbox(label="New title", placeholder="What should we call it?")
        rename_btn = gr.Button("✏️ Rename")
        delete_picker = gr.Dropdown(label="Delete a track", choices=_song_choices())
        delete_btn = gr.Button("🗑️ Delete", variant="stop")
        refresh_btn = gr.Button("↻ Refresh")

    gr.Markdown("---\n🏔️ **CU Boulder Flatirons** · built with the class services on `dobolyi.com`")

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

    create_btn.click(
        create_song,
        inputs=[title_box, genre_choice, genre_custom, mood_multi, mood_custom,
                vocal_radio, vocal_style, energy_slider, bpm_slider, key_choice,
                tsig_choice, lyrics_box, duration_slider, thinking_box, show_picker],
        outputs=[song_audio, cover_img, create_report, show_picker,
                 library_gallery, delete_picker, rename_picker],
    )

    build_btn.click(
        build_show,
        inputs=[show_picker, voice_ref],
        outputs=[show_audio, show_covers, show_cue, jukebox_viz],
    )

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
    )

    delete_btn.click(delete_song, inputs=[delete_picker, show_picker],
                     outputs=[library_table, show_picker, delete_picker,
                              rename_picker, library_gallery])
    refresh_btn.click(refresh_library, inputs=[show_picker],
                      outputs=[library_table, show_picker, delete_picker,
                               rename_picker, library_gallery])


if __name__ == "__main__":
    demo.launch(
        server_name=os.environ.get("AIJ_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("AIJ_PORT", "7860")),
        share=os.environ.get("AIJ_SHARE", "0") == "1",
    )
