"""Unit tests for the LLM client (port 9001)."""
import pytest

from ai_jukebox import config, http, llm


@pytest.fixture
def fake_llm(monkeypatch):
    """Records the JSON payload; returns canned chat content."""
    captured = {}

    def fake_post_json(url, payload, timeout=120):
        captured["url"] = url
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "\n\nprobe-ok\n"}}]}

    monkeypatch.setattr(http, "post_json", fake_post_json)
    return captured


def test_chat_returns_stripped_content(fake_llm):
    assert llm.chat([{"role": "user", "content": "hi"}]) == "probe-ok"


def test_chat_always_disables_thinking(fake_llm):
    llm.chat([{"role": "user", "content": "hi"}])
    assert fake_llm["payload"]["chat_template_kwargs"] == {"thinking": False}


def test_chat_uses_class_model_and_2048_budget(fake_llm):
    llm.chat([{"role": "user", "content": "hi"}])
    assert fake_llm["payload"]["model"] == config.LLM_MODEL
    assert fake_llm["payload"]["max_tokens"] == 2048 or fake_llm["payload"]["max_tokens"] > 0


def test_chat_raises_on_empty_content(monkeypatch):
    monkeypatch.setattr(
        http, "post_json",
        lambda *a, **k: {"choices": [{"message": {"content": None}}]},
    )
    with pytest.raises(http.ServiceError, match="retries"):
        llm.chat([{"role": "user", "content": "hi"}], _attempt=3)


def test_chat_retries_with_larger_budget_on_empty(monkeypatch):
    calls = []

    def fake(url, payload, timeout=120):
        calls.append(payload["max_tokens"])
        content = "ok now" if len(calls) == 2 else None
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(http, "post_json", fake)
    assert llm.chat([{"role": "user", "content": "hi"}], max_tokens=1024) == "ok now"
    assert calls == [1024, 2048]


def test_write_lyrics_includes_theme(fake_llm):
    out = llm.write_lyrics("Neon Afterglow", "synthwave", "late-night drive")
    assert "Neon Afterglow" in fake_llm["payload"]["messages"][-1]["content"]
    assert "late-night drive" in fake_llm["payload"]["messages"][-1]["content"]


def test_write_lyrics_vocal_style_shapes_system_prompt(fake_llm):
    llm.write_lyrics("Duet Song", "pop", "romantic", vocal_style="Duet (two voices)")
    system = fake_llm["payload"]["messages"][0]["content"]
    assert "Duet (two voices)" in system
    assert "two voiced" in system


def test_write_lyrics_auto_vocal_style_ignored(fake_llm):
    llm.write_lyrics("Song", "pop", "fun", vocal_style="Auto")
    system = fake_llm["payload"]["messages"][0]["content"]
    assert "vocal performance is:" not in system


def test_write_cover_prompt_asks_for_no_text(fake_llm):
    llm.write_cover_prompt("T", "rock", "dark", "lyrics here")
    user_msg = fake_llm["payload"]["messages"][-1]["content"]
    assert "lyrics here" in user_msg
    assert "text" in fake_llm["payload"]["messages"][0]["content"]


def test_write_dj_script_mentions_both_tracks(fake_llm):
    llm.write_dj_script("Old Track", "pop", "New Track", "jazz")
    user_msg = fake_llm["payload"]["messages"][-1]["content"]
    assert "Old Track" in user_msg and "New Track" in user_msg
