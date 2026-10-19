"""AI Jukebox — Gradio UI.

Tabs:
  1. Create — describe a song (vocal or instrumental); the app writes lyrics
     (9001), produces the track (9007), and designs cover art (9006).
  2. Jukebox — pick tracks, optionally upload an MP3/WAV voice reference,
     build a show of spoken DJ commentary (9001 + 9008) between songs, and
     play it as ONE continuous mix (play/pause/skip controls; the queue
     advances automatically; speech never overlaps music), with a cue sheet
     and per-track covers.
  3. Library — browse, refresh, and delete generated tracks.

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


# ---------------------------------------------------------------- Create tab

def create_song(title, genre, mood, vocal_choice, custom_lyrics, duration, thinking,
                progress=gr.Progress()):
    title = (title or "").strip() or "Untitled Song"
    genre = (genre or "").strip() or "upbeat indie pop"
    mood = (mood or "").strip() or "hopeful and sunny"
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
        )
    except Exception as e:  # surfaced in the UI, never the terminal
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
    lines.append("\n_Track added to the library — pick it in the Jukebox tab._")
    return song.audio_path, song.cover_path, "\n".join(lines), _dropdown_update(), _gallery_update()


# --------------------------------------------------------------- Jukebox tab

def _format_ts(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def build_show(selected_ids, voice_ref):
    songs = [s for s in library.all() if s.id in (selected_ids or [])]
    if not songs:
        return (None, gr.Gallery(value=[], columns=3, height=200),
                "⚠️ Pick at least one track, then press **Build the show**.")
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
    return (
        mixed,
        gr.Gallery(value=gallery_items, columns=max(1, len(gallery_items)), height=200),
        "\n".join(lines),
    )


# -------------------------------------------------------------- Library tab

def delete_song(song_id):
    if song_id:
        library.delete(song_id)
    return _df_update(), _dropdown_update(), _gallery_update()


def refresh_library():
    return _df_update(), _dropdown_update(), _gallery_update()


# ---------------------------------------------------------------------- UI

with gr.Blocks(title="AI Jukebox", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# 🎵 AI Jukebox\n"
        "Generate a song, its cover art, and a spoken DJ set — all on the class "
        "services (LLM 9001 · FLUX cover art 9006 · ACE-Step music 9007 · Chatterbox "
        "voice 9008). Port 9000 is never used.\n"
        + ("_3 sample tracks preloaded for instant playback._" if _seeded else "")
    )

    with gr.Tabs():
        # ---------------- Create ----------------
        with gr.Tab("Create a song"):
            with gr.Row():
                with gr.Column(scale=1):
                    title_box = gr.Textbox(label="Title", placeholder="Neon Afterglow")
                    genre_box = gr.Textbox(label="Genre / style", value="upbeat indie pop",
                                           placeholder="e.g. dreamy synthwave ballad")
                    mood_box = gr.Textbox(label="Mood / theme", value="hopeful and sunny",
                                          placeholder="e.g. late-night drive through the city")
                    vocal_radio = gr.Radio(choices=["Vocal", "Instrumental"], value="Vocal",
                                           label="Track type")
                    lyrics_box = gr.Textbox(
                        label="Custom lyrics (optional, vocal tracks — blank = AI-written)",
                        lines=6, placeholder="[Verse 1]\n…")
                    with gr.Row():
                        duration_slider = gr.Slider(8, 60, value=20, step=2,
                                                    label="Track length (seconds)")
                        thinking_box = gr.Checkbox(label="LM planning (slower, richer)",
                                                   value=False)
                    create_btn = gr.Button("🎬 Generate song + cover", variant="primary")
                with gr.Column(scale=1):
                    song_audio = gr.Audio(label="Your song", type="filepath")
                    cover_img = gr.Image(label="Cover art", type="filepath", height=300)
            create_report = gr.Markdown("")

        # ---------------- Jukebox ----------------
        with gr.Tab("Jukebox show"):
            gr.Markdown(
                "Pick tracks (in play order) and **Build the show**. The DJ — Qwen-written, "
                "spoken by Chatterbox — introduces every track; the show is mixed into **one "
                "continuous track** with play/pause/skip controls: the queue advances "
                "automatically and speech never overlaps music. Upload an **MP3/WAV voice "
                "reference** to clone the DJ's voice, or leave it empty for the default voice."
            )
            with gr.Row():
                show_picker = gr.Dropdown(label="Tracks for the show (in order)", multiselect=True,
                                          choices=_song_choices())
                voice_ref = gr.Audio(label="DJ voice reference (optional MP3/WAV)",
                                     type="filepath")
                build_btn = gr.Button("🎙️ Build the show", variant="primary")
            show_audio = gr.Audio(label="Show (continuous mix)", type="filepath", autoplay=True)
            show_cue = gr.Markdown("")
            show_covers = gr.Gallery(label="Tracks in this show", columns=3, height=200)

        # ---------------- Library ----------------
        with gr.Tab("Library"):
            library_gallery = gr.Gallery(label="All tracks", columns=3, height=220,
                                         value=_library_gallery_items())
            library_table = gr.Dataframe(headers=LIBRARY_HEADERS, type="array",
                                         value=_library_rows())
            with gr.Row():
                delete_picker = gr.Dropdown(label="Delete a track", choices=_song_choices())
                delete_btn = gr.Button("🗑️ Delete", variant="stop")
                refresh_btn = gr.Button("↻ Refresh")

    # -- wiring ---------------------------------------------------------
    create_btn.click(
        create_song,
        inputs=[title_box, genre_box, mood_box, vocal_radio, lyrics_box,
                duration_slider, thinking_box],
        outputs=[song_audio, cover_img, create_report, show_picker, library_gallery],
    )

    build_btn.click(
        build_show,
        inputs=[show_picker, voice_ref],
        outputs=[show_audio, show_covers, show_cue],
    )

    delete_btn.click(delete_song, inputs=[delete_picker],
                     outputs=[library_table, delete_picker, library_gallery])
    refresh_btn.click(refresh_library, inputs=[],
                      outputs=[library_table, delete_picker, library_gallery])


if __name__ == "__main__":
    demo.launch(
        server_name=os.environ.get("AIJ_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("AIJ_PORT", "7860")),
        share=os.environ.get("AIJ_SHARE", "0") == "1",
    )
