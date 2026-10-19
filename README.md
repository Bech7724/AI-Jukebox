# 🎵 AI Jukebox

Generate a **song**, its **cover art**, and a full **jukebox show with a spoken DJ**
— every AI feature runs on the class model services (`dobolyi.com` ports
9001 / 9006 / 9007 / 9008, see `class-endpoints.txt`). Port 9000 is reserved
for agentic use and is **never** used by this app.

## Features

1. **Customizable song generation** — describe a genre + mood (or paste your own
   lyrics); the class LLM writes structured, singable lyrics and **ACE-Step 1.5
   XL Turbo** (9007) renders the track (MP3).
2. **Matching cover art** — the LLM turns your song into an album-cover prompt and
   **FLUX.2-klein-4B** (9006) paints a square cover, saved beside the track.
3. **Jukebox with DJ commentary** — pick tracks from the library, build a show:
   the DJ (LLM 9001 writing, **Chatterbox V3** 9008 speaking) introduces every
   track, so **spoken commentary plays between songs**, then step through the
   show with autoplay.

## Service map

| Port | Model (per class-endpoints.txt) | Used for | API |
| --- | --- | --- | --- |
| 9001 | `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` | lyrics, cover prompt, DJ script | vLLM `/v1/chat/completions` |
| 9006 | `black-forest-labs/FLUX.2-klein-4B` | cover art | vLLM-Omni `/v1/images/generations` |
| 9007 | `ACE-Step/acestep-v15-xl-turbo` | music (async task API) | `release_task` → poll → download |
| 9008 | Chatterbox Multilingual V3 | DJ voice | `/v1/audio/speech` |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in AIJ_API_KEY from class-endpoints.txt
python app.py                 # http://127.0.0.1:7860
```

> **Credentials stay server-side.** The class API key lives only in your local
> `.env` (gitignored). It is never committed, printed, logged, or written into
> docs, browser code, or archives. The app refuses to make requests until a key
> is set.

## Usage

- **Create a song**: title + genre + mood → *Generate*. Lyrics are auto-written
  by the LLM (or paste your own), the track is produced (longer lengths take
  longer — ACE-Step is an async task API), and the cover is painted. Every step
  is logged in the UI.
- **Jukebox show**: select tracks → *Build the show* → *Next ▶*. Each segment
  autoplays: DJ intro → song → DJ intro → song…
- **Library**: browse track metadata and delete tracks. All generated content
  lives in `data/` (gitignored — nothing generated is ever committed).

## Tests

```bash
python -m pytest -q
```

Unit tests mock every class service (no network needed); CI runs them on push.

## Layout

```
app.py                 Gradio UI (Create / Jukebox / Library)
ai_jukebox/
  config.py            env-driven config (host, ports, models, key)
  http.py              auth'd HTTP helpers (stdlib only)
  llm.py               9001 chat + lyrics/cover/DJ prompt writers
  image.py             9006 FLUX cover art
  music.py             9007 ACE-Step async generation
  tts.py               9008 Chatterbox speech
  dj.py                show builder: script + spoken intros
  library.py           on-disk song library (JSON index + assets)
  pipeline.py          orchestration for one full track
tests/                 unit tests with mocked services
```

## Compliance

- No paid services anywhere (core or optional) — class services and the class
  key alone.
- No third-party music, lyrics, cover art, or voice samples are bundled; every
  asset is generated live by the class services.
- User uploads/recordings are never part of this repo — keep them out of commits
  and submission archives too (they land in `data/`, gitignored).
- No credential material in any committed file: `AIJ_API_KEY` is set per
  developer in `.env`.
