"""DJ commentary: the class LLM writes the script, Chatterbox speaks it.

The jukebox "show" is a sequence of segments — a spoken DJ intro
(script + TTS audio) followed by each track — so commentary always plays
*between* songs.
"""
from __future__ import annotations

from pathlib import Path

from . import llm, tts
from .library import Library, Song


def write_script(previous: Song | None, next_track: Song) -> str:
    return llm.write_dj_script(
        previous.title if previous else None,
        previous.genre if previous else None,
        next_track.title,
        next_track.genre,
    )


def make_intro(library: Library, previous: Song | None, next_track: Song,
               voice_ref_b64: str | None = None) -> tuple[str, Path]:
    """Write + speak a DJ intro for `next_track`; returns (script, saved mp3 path).

    `voice_ref_b64` optionally clones the DJ's voice from a base64 MP3/WAV
    snippet; None uses the service's default voice.
    """
    script = write_script(previous, next_track)
    audio = tts.synthesize(script, ref_audio_b64=voice_ref_b64)
    out = library.intro_path(next_track.id)
    out.write_bytes(audio)
    return script, out


def build_show(library: Library, songs: list[Song],
               voice_ref_b64: str | None = None) -> list[dict]:
    """Build a full show: [intro, song, intro, song, …].

    Each segment dict has:
      kind  = "intro" | "song"
      id/subtitle/label for the UI
      audio = path to the audio file
      cover = path | None (song segments)
      script = DJ script text (intro segments)
    All intros are generated eagerly so the show plays without further
    LLM/TTS calls mid-playback. `voice_ref_b64` customizes the DJ voice
    (None -> default voice).
    """
    segments: list[dict] = []
    for i, song in enumerate(songs):
        previous = songs[i - 1] if i > 0 else None
        script, intro_file = make_intro(library, previous, song, voice_ref_b64=voice_ref_b64)
        segments.append(
            {
                "kind": "intro",
                "label": "DJ interlude",
                "audio": str(intro_file),
                "script": script,
                "cover": None,
            }
        )
        segments.append(
            {
                "kind": "song",
                "label": f'{song.title} · {song.genre}',
                "audio": song.audio_path,
                "cover": song.cover_path,
                "script": "",
                "song_id": song.id,
            }
        )
    return segments
