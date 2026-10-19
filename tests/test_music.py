"""Unit tests for the ACE-Step music client (port 9007)."""
import json

import pytest

from ai_jukebox import http, music


def _release_task_response(task_id="task-abc"):
    return {"data": {"task_id": task_id, "status": "queued", "queue_position": 1},
            "code": 200, "error": None}


def _query_result_response(task_id="task-abc", status=1, file_path="/v1/audio?path=%2Fx.mp3"):
    return {
        "data": [{
            "task_id": task_id,
            "status": status,
            "result": json.dumps([{"file": file_path, "metas": {"bpm": 120, "duration": 12.0}}]),
        }],
        "code": 200, "error": None,
    }


class FakeTransport:
    def __init__(self, query_responses):
        self.query_responses = list(query_responses)
        self.calls = []

    def post_json(self, url, payload, timeout=120):
        self.calls.append((url, payload))
        if url.endswith("/release_task"):
            return _release_task_response()
        if url.endswith("/query_result"):
            return self.query_responses.pop(0)
        raise AssertionError(f"unexpected POST {url}")

    def get_raw(self, url, timeout=180):
        self.calls.append((url, None))
        assert url.startswith("http") and "v1/audio" in url
        return b"ID3-fake-audio-bytes"


def test_generate_song_full_flow(monkeypatch):
    t = FakeTransport([_query_result_response()])
    monkeypatch.setattr(http, "post_json", t.post_json)
    monkeypatch.setattr(http, "get_raw", t.get_raw)

    out = music.generate_song(prompt="upbeat pop", lyrics="la la", duration=12)
    assert out["audio"] == b"ID3-fake-audio-bytes"
    assert out["meta"]["metas"]["bpm"] == 120

    release_payload = t.calls[0][1]
    assert release_payload["prompt"] == "upbeat pop"
    assert release_payload["lyrics"] == "la la"
    assert release_payload["duration"] == 12
    assert release_payload["thinking"] is False


def test_generate_song_polls_until_done(monkeypatch):
    t = FakeTransport([_query_result_response(status=0), _query_result_response(status=1)])
    monkeypatch.setattr(http, "post_json", t.post_json)
    monkeypatch.setattr(http, "get_raw", t.get_raw)
    out = music.generate_song(prompt="p", poll_every=0.01)
    assert out["audio"] == b"ID3-fake-audio-bytes"


def test_generate_song_propagates_failure(monkeypatch):
    t = FakeTransport([_query_result_response(status=2)])
    monkeypatch.setattr(http, "post_json", t.post_json)
    with pytest.raises(http.ServiceError, match="failed"):
        music.generate_song(prompt="p", poll_every=0.01)


def test_generate_song_rejects_missing_task_id(monkeypatch):
    def bad_release(url, payload, timeout=120):
        return {"data": {}, "code": 200, "error": None}

    monkeypatch.setattr(http, "post_json", bad_release)
    with pytest.raises(http.ServiceError, match="task id"):
        music.generate_song(prompt="p")
