"""High-level orchestration used by the UI: produce tracks, run the show."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass

from . import config, image, llm, music
from .library import Library, Song, slugify


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "failed"
    detail: str = ""
    seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def generate_song(library: Library, title: str, genre: str, mood: str,
                  duration: int = 30, custom_lyrics: str | None = None,
                  thinking: bool = False, vocal: bool = True,
                  progress_cb: Callable[[str], None] | None = None,
                  energy: int | None = None, bpm: int | None = None,
                  key_scale: str | None = None, time_signature: str | None = None,
                  vocal_style: str = "") -> tuple[Song, list[StepResult]]:
    """Produce one full track: lyrics -> music -> cover art.

    `vocal=True` generates (or accepts) lyrics for a sung track; `vocal=False`
    produces an instrumental (no lyrics sent to ACE-Step). Optional styling:
    `energy` (1-10) and `vocal_style` are woven into the music prompt; `bpm`,
    `key_scale`, and `time_signature` are sent to ACE-Step (verified live).
    Cover-art failure is non-fatal (the track is still saved, with no cover);
    music failure aborts because a track without audio is useless.
    `progress_cb` (optional) receives a human-readable step name as each stage
    begins. Returns the saved Song plus a step log for the UI.
    """
    steps: list[StepResult] = []

    def _step(name: str) -> None:
        if progress_cb is not None:
            progress_cb(name)

    # 1) Lyrics ---------------------------------------------------------
    _step("Lyrics")
    if not vocal:
        lyrics = ""
        lyrics_mode = "INSTRUMENTAL"
        steps.append(StepResult("lyrics", "ok", "Instrumental track — no vocal lyrics", 0.0))
    elif custom_lyrics and custom_lyrics.strip():
        lyrics = custom_lyrics.strip()
        steps.append(StepResult("lyrics", "ok", "Used custom lyrics", 0.0))
        lyrics_mode = "CUSTOM_LYRICS"
    else:
        t = time.time()
        lyrics = llm.write_lyrics(title, genre, mood, vocal_style=vocal_style)
        steps.append(
            StepResult("lyrics", "ok", f"Generated {len(lyrics.split())} words", time.time() - t)
        )
        lyrics_mode = "AUTO_LYRICS"

    # 2) Cover-art prompt ------------------------------------------------
    _step("Cover art prompt")
    t = time.time()
    cover_prompt = llm.write_cover_prompt(title, genre, mood, lyrics)
    steps.append(StepResult("cover-prompt", "ok", cover_prompt, time.time() - t))

    # 3) Music -----------------------------------------------------------
    _step("Music (ACE-Step)")
    energy_word = ""
    if energy:
        for lo, hi, word in ((1, 3, "very relaxed"), (3, 5, "laid-back"),
                             (5, 7, "moderate energy"), (7, 9, "upbeat"),
                             (9, 11, "very high-energy")):
            if lo <= int(energy) < hi:
                energy_word = word
                break
    style_word = vocal_style.strip() if (vocal and vocal_style.strip()
                                         and vocal_style.strip().lower() != "auto") else ""
    music_prompt = ", ".join(
        p for p in (genre, mood, energy_word, style_word) if p
    ).strip(", ") or f"{genre}, {mood}"
    t = time.time()
    result = music.generate_song(
        prompt=music_prompt, lyrics=lyrics, duration=duration, thinking=thinking,
        bpm=bpm, key_scale=key_scale, time_signature=time_signature,
    )
    steps.append(StepResult("music", "ok", f"{int(duration)}s track · {music_prompt}", time.time() - t))

    song = Song(
        id=Library.new_song_id(title),
        title=title,
        genre=genre,
        mood=mood,
        created=time.time(),
        audio_path="",
        cover_path=None,
        lyrics=lyrics,
        cover_prompt=cover_prompt,
        music_prompt=music_prompt,
        meta=result["meta"],
        lyrics_mode=lyrics_mode,
        vocal=vocal,
    )
    song_dir = library.song_dir(song.id)
    song_dir.mkdir(parents=True, exist_ok=True)
    audio_path = song_dir / "song.mp3"
    audio_path.write_bytes(result["audio"])
    song.audio_path = str(audio_path)

    # 4) Cover art (non-fatal) -------------------------------------------
    _step("Cover art (FLUX)")
    try:
        t = time.time()
        cover = image.generate_cover(cover_prompt)
        cover_path = song_dir / "cover.png"
        cover_path.write_bytes(cover["image"])
        song.cover_path = str(cover_path)
        detail = "1024x1024 PNG"
        if cover.get("revised_prompt"):
            detail += f" | FLUX revision: {cover['revised_prompt'][:140]}"
        steps.append(StepResult("cover-art", "ok", detail, time.time() - t))
    except Exception as e:  # noqa: BLE001 — cover art is optional polish
        steps.append(StepResult("cover-art", "failed", str(e)[:300], 0.0, str(e)))

    library.add(song)
    return song, steps
