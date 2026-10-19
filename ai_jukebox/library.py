"""Local song library: a JSON metadata index plus on-disk assets.

Every generated track gets its own directory under data/songs/<song_id>/
holding the audio and cover art; the index (data/library.json) is the
source of truth for the jukebox UI.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "song")[:max_len]


def _default_samples_root() -> Path:
    """Repo-root/samples — the bundled, pre-generated sample library."""
    return Path(config.DATA_DIR).parent / "samples"


@dataclass
class Song:
    id: str
    title: str
    genre: str
    mood: str
    created: float
    audio_path: str
    cover_path: str | None = None
    lyrics: str = ""
    cover_prompt: str = ""
    music_prompt: str = ""
    meta: dict = field(default_factory=dict)
    lyrics_mode: str = "AUTO_LYRICS"  # AUTO_LYRICS | CUSTOM_LYRICS | INSTRUMENTAL
    vocal: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Song":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def music_metas(self) -> dict:
        """The ACE-Step 'metas' block (bpm, keyscale, timesignature, …)."""
        m = self.meta.get("metas") or {}
        return m if isinstance(m, dict) else {}


class Library:
    """Thread-safe JSON-indexed collection of Song records + asset files."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or config.DATA_DIR)
        self.index_path = self.root / "library.json"
        self._lock = threading.Lock()
        (self.root / "songs").mkdir(parents=True, exist_ok=True)
        (self.root / "dj").mkdir(parents=True, exist_ok=True)

    # -- persistence ----------------------------------------------------
    def _load(self) -> list[dict]:
        try:
            return json.loads(self.index_path.read_text())
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []  # corrupt index -> start clean (assets on disk survive)

    def _save(self, items: list[dict]) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=2))
        tmp.replace(self.index_path)

    # -- CRUD -----------------------------------------------------------
    def add(self, song: Song) -> Song:
        with self._lock:
            items = self._load()
            items = [i for i in items if i["id"] != song.id]
            items.append(song.to_dict())
            self._save(items)
        return song

    def get(self, song_id: str) -> Song | None:
        for i in self._load():
            if i["id"] == song_id:
                return Song.from_dict(i)
        return None

    def all(self) -> list[Song]:
        songs = [Song.from_dict(i) for i in self._load()]
        songs.sort(key=lambda s: s.created, reverse=True)
        return songs

    def delete(self, song_id: str) -> bool:
        with self._lock:
            items = self._load()
            kept = [i for i in items if i["id"] != song_id]
            if len(kept) == len(items):
                return False
            self._save(kept)
        song_dir = self.root / "songs" / song_id
        if song_dir.exists():
            shutil.rmtree(song_dir, ignore_errors=True)
        (self.root / "dj" / f"{song_id}.intro.mp3").unlink(missing_ok=True)
        return True

    def rename(self, song_id: str, new_title: str) -> bool:
        """Retitle a track in the index (files keep their stable id)."""
        new_title = (new_title or "").strip()
        if not new_title:
            return False
        with self._lock:
            items = self._load()
            for it in items:
                if it["id"] == song_id:
                    old = it.get("title")
                    it["title"] = new_title
                    it.setdefault("meta", {})
                    if old:
                        it["meta"]["renamed_from"] = old
                    self._save(items)
                    return True
        return False

    # -- asset paths ----------------------------------------------------
    def song_dir(self, song_id: str) -> Path:
        return self.root / "songs" / song_id

    def intro_path(self, song_id: str) -> Path:
        return self.root / "dj" / f"{song_id}.intro.mp3"

    @staticmethod
    def new_song_id(title: str) -> str:
        return f"{slugify(title)}-{uuid.uuid4().hex[:6]}"


def seed_samples(library: Library | None = None,
                 samples_root: str | Path | None = None) -> int:
    """Copy the bundled sample tracks into an empty library; returns count.

    Samples are pre-generated with the class endpoints (AI-written lyrics
    only) and ship inside the repo under samples/. They are only seeded when
    the data library is empty, so user work is never overwritten. Assets are
    copied into the gitignored data/ tree like any generated track.
    """
    root = Path(samples_root) if samples_root else _default_samples_root()
    index = root / "library.json"
    if not index.exists():
        return 0
    lib = library or Library()
    if lib.all():
        return 0  # never clobber an existing library

    items = json.loads(index.read_text())
    seeded = 0
    for it in items:
        song = Song.from_dict(it)
        src_audio = root / it["audio_path"]
        src_cover = root / it["cover_path"] if it.get("cover_path") else None
        if not src_audio.exists():
            continue
        dst = lib.song_dir(song.id)
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_audio, dst / src_audio.name)
        song.audio_path = str(dst / src_audio.name)
        if src_cover and src_cover.exists():
            shutil.copy2(src_cover, dst / src_cover.name)
            song.cover_path = str(dst / src_cover.name)
        song.created = time.time()
        lib.add(song)
        seeded += 1
    return seeded
