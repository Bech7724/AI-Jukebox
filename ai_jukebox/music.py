"""Client for the class ACE-Step music service (port 9007).

ACE-Step 1.5 XL Turbo exposes an *asynchronous* task API:
  1. POST /release_task   -> {"data": {"task_id": ...}}
  2. POST /query_result   -> status 0 (running) / 1 (done) / 2 (failed);
                             on success `result` is a JSON *string* with the
                             audio-file info.
  3. GET  /v1/audio?path=...  -> the generated audio file.

Verified end-to-end against the live service (12 s mp3 track in ~15 s).
"""
from __future__ import annotations

import json
import time

from . import config, http


def generate_song(prompt: str, lyrics: str = "", duration: int = 30,
                  audio_format: str = "mp3", thinking: bool = False,
                  model: str | None = None, vocal_language: str = "en",
                  poll_every: float = 5.0, timeout: int = 420) -> dict:
    """Generate a song from a text description and optional lyrics.

    Returns {"audio": <bytes>, "meta": {…}} where meta carries the server's
    generation info (metas / seed / models). Raises ServiceError on failure.
    """
    base = config.base_url(config.MUSIC_PORT)
    payload: dict = {
        "prompt": prompt,
        "lyrics": lyrics or "",
        "vocal_language": vocal_language,
        "audio_format": audio_format,
        "duration": int(duration),
        "thinking": bool(thinking),
    }
    if model:
        payload["model"] = model

    resp = http.post_json(f"{base}/release_task", payload, timeout=120)
    task_id = (resp.get("data") or {}).get("task_id")
    if not task_id:
        raise http.ServiceError(f"ACE-Step did not return a task id: {str(resp)[:300]}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_every)
        q = http.post_json(f"{base}/query_result", {"task_id_list": [task_id]}, timeout=120)
        rows = q.get("data") or []
        if not rows:
            continue
        row = rows[0]
        status = row.get("status")
        if status == 2:
            raise http.ServiceError(
                f"ACE-Step generation failed for task {task_id}: {str(row)[:400]}"
            )
        if status == 1:
            info = _parse_result(row)
            file_url = info["file"]
            if file_url.startswith("/"):
                file_url = f"{base}{file_url}"
            audio = http.get_raw(file_url, timeout=180)
            if not audio:
                raise http.ServiceError("ACE-Step returned an empty audio file.")
            meta = {
                k: info.get(k)
                for k in ("metas", "prompt", "lyrics", "seed_value", "lm_model", "dit_model")
                if info.get(k) is not None
            }
            meta["duration_requested"] = int(duration)
            meta["audio_format"] = audio_format
            return {"audio": audio, "meta": meta}

    raise http.ServiceError(f"ACE-Step task {task_id} did not finish within {timeout}s.")


def _parse_result(row: dict) -> dict:
    try:
        info = json.loads(row["result"])
    except (KeyError, json.JSONDecodeError) as e:
        raise http.ServiceError(f"Malformed ACE-Step result payload: {str(row)[:300]}") from e
    if isinstance(info, list):
        info = info[0] if info else {}
    if not isinstance(info, dict) or "file" not in info:
        raise http.ServiceError(f"ACE-Step result missing audio file info: {str(info)[:300]}")
    return info
