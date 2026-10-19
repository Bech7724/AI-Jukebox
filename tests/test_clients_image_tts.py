"""Unit tests for the FLUX image client (port 9006) and TTS client (9008)."""
import base64

import pytest

from ai_jukebox import http, image, tts
from ai_jukebox import config


class TestImage:
    def test_generate_cover_decodes_b64(self, monkeypatch):
        png = b"\x89PNG\r\n\x1a\nfakeimage"
        def fake_post_json(url, payload, timeout=120):
            return {"data": [{"b64_json": base64.b64encode(png).decode(), "revised_prompt": "r"}]}
        monkeypatch.setattr(http, "post_json", fake_post_json)
        out = image.generate_cover("a cover prompt")
        assert out["image"] == png
        assert out["revised_prompt"] == "r"

    def test_generate_cover_falls_back_to_url(self, monkeypatch):
        monkeypatch.setattr(http, "post_json",
                            lambda *a, **k: {"data": [{"url": "http://x/a.png"}]})
        monkeypatch.setattr(http, "get_raw", lambda *a, **k: b"url-bytes")
        assert image.generate_cover("p")["image"] == b"url-bytes"

    def test_generate_cover_sends_flux_model(self, monkeypatch):
        captured = {}
        def fake_post_json(url, payload, timeout=120):
            captured.update(payload)
            return {"data": [{"b64_json": base64.b64encode(b"x").decode()}]}
        monkeypatch.setattr(http, "post_json", fake_post_json)
        image.generate_cover("p")
        assert captured["model"] == config.IMAGE_MODEL
        assert captured["n"] == 1

    def test_generate_cover_raises_on_empty_payload(self, monkeypatch):
        monkeypatch.setattr(http, "post_json",
                            lambda *a, **k: {"data": [{}]})
        with pytest.raises(http.ServiceError):
            image.generate_cover("p")


class TestTTS:
    def test_synthesize_returns_bytes(self, monkeypatch):
        captured = {}
        def fake_post_raw(url, payload, timeout=300):
            captured.update(payload)
            return b"ID3ttsbytes"
        monkeypatch.setattr(http, "post_raw", fake_post_raw)
        out = tts.synthesize("Hello there")
        assert out == b"ID3ttsbytes"
        assert captured["model"] == config.TTS_MODEL
        assert captured["input"] == "Hello there"
        assert captured["language_id"] == "en"
        assert captured["response_format"] == "mp3"

    def test_synthesize_raises_on_empty(self, monkeypatch):
        monkeypatch.setattr(http, "post_raw", lambda *a, **k: b"")
        with pytest.raises(http.ServiceError):
            tts.synthesize("x")


class TestVoiceCloning:
    def test_ref_audio_sent_with_default_voice(self, monkeypatch):
        captured = {}

        def fake_post_raw(url, payload, timeout=300):
            captured.update(payload)
            return b"ID3clone"

        monkeypatch.setattr(http, "post_raw", fake_post_raw)
        out = tts.synthesize("Clone me", ref_audio_b64="QUJDRA==")
        assert out == b"ID3clone"
        assert captured["ref_audio"] == "QUJDRA=="
        assert captured["voice"] == "default"  # cloning rides default voice

    def test_no_ref_audio_omits_field(self, monkeypatch):
        captured = {}

        def fake_post_raw(url, payload, timeout=300):
            captured.update(payload)
            return b"ID3"

        monkeypatch.setattr(http, "post_raw", fake_post_raw)
        tts.synthesize("Plain")
        assert "ref_audio" not in captured
