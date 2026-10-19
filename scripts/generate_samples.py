#!/usr/bin/env python3
"""Regenerate the bundled sample library (samples/) with the class endpoints.

Run from the repo root with a configured .env:
    .venv/bin/python scripts/generate_samples.py

Produces samples/library.json plus one directory per track (audio + cover).
The samples are committed so a fresh clone can play them immediately; sample
lyrics are AI-written by the class LLM (9001) — no third-party content.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_jukebox import pipeline
from ai_jukebox.library import Library

SAMPLES = [
    {"title": "Neon Afterglow", "genre": "synthwave",
     "mood": "late-night drive through neon-lit streets", "duration": 16, "vocal": True},
    {"title": "Morning Gold", "genre": "upbeat indie pop",
     "mood": "first light over the bay, full of hope", "duration": 16, "vocal": True},
    {"title": "Midnight Café", "genre": "lo-fi jazz",
     "mood": "rain on the window, cozy and warm", "duration": 16, "vocal": False},
]


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "samples"
    stage = Library(str(root / "_stage"))

    records = []
    for spec in SAMPLES:
        song, steps = pipeline.generate_song(
            stage, spec["title"], spec["genre"], spec["mood"],
            duration=spec["duration"], vocal=spec["vocal"], thinking=False,
        )
        music_step = next(s for s in steps if s.name == "music")
        cover_step = next((s for s in steps if s.name == "cover-art"), None)

        dst = root / song.id
        dst.mkdir(parents=True, exist_ok=True)
        audio = Path(song.audio_path)
        (dst / audio.name).write_bytes(audio.read_bytes())
        rel_audio = f"{song.id}/{audio.name}"
        rel_cover = ""
        if song.cover_path:
            cover = Path(song.cover_path)
            (dst / cover.name).write_bytes(cover.read_bytes())
            rel_cover = f"{song.id}/{cover.name}"

        d = song.to_dict()
        d.update({"audio_path": rel_audio, "cover_path": rel_cover or None,
                  "created": time.time()})
        records.append(d)
        print(f"OK  {song.title:16s} {song.genre:18s} vocal={song.vocal} "
              f"music={music_step.seconds:5.1f}s "
              f"cover={('ok' if cover_step and cover_step.status == 'ok' else 'FAILED')} "
              f"lyrics={len(song.lyrics)} chars")

    (root / "library.json").write_text(json.dumps(records, indent=2))
    print(f"\nWrote {root / 'library.json'} with {len(records)} samples.")

    import shutil
    stage_dir = root / "_stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir, ignore_errors=True)
        print("Cleaned scratch area samples/_stage/.")


if __name__ == "__main__":
    main()
