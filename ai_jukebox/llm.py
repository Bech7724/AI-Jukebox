"""Client for the class LLM (port 9001 — Qwen3.6-35B-A3B served by vLLM).

The Qwen3 chat template must run with reasoning disabled
(chat_template_kwargs={"thinking": False}) and a generous max_tokens,
otherwise the model spends its reply budget on reasoning and `content`
comes back null. Verified against the live service.
"""
from __future__ import annotations

from . import config, http


def chat(messages: list[dict], max_tokens: int = 2048, temperature: float = 0.8,
         timeout: int = 240, _attempt: int = 0) -> str:
    """One chat-completion round trip; returns trimmed text content.

    The Qwen3 reasoning pass runs even with chat_template_kwargs thinking
    disabled: when it consumes the whole token budget the reply comes back
    with empty content (finish_reason "length", reasoning_tokens ==
    max_tokens). We therefore retry with a larger budget until content
    arrives, capped at a few attempts.
    """
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"thinking": False},
    }
    data = http.post_json(
        f"{config.base_url(config.LLM_PORT)}/v1/chat/completions", payload, timeout=timeout
    )
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError) as e:
        raise http.ServiceError(f"Unexpected LLM response: {str(data)[:300]}") from e
    if content and content.strip():
        return content.strip()
    if _attempt < 3:
        return chat(messages, max_tokens=int(max_tokens * 2), temperature=temperature,
                    timeout=timeout, _attempt=_attempt + 1)
    raise http.ServiceError(
        "LLM returned empty content after retries (the 35B reasoning pass kept "
        "consuming the token budget). Try again later or lower the temperature."
    )


def write_lyrics(title: str, genre: str, mood: str, structure: str = "ABABCB",
                 vocal_style: str = "") -> str:
    """Original, singable lyrics with structure tags for the music model.

    `vocal_style` (e.g. "Duet (two voices)") adds a performance instruction
    that also shapes the lyric form (two-part dialogue, anthemic chorus, …).
    """
    style_note = ""
    if vocal_style and vocal_style.strip() and vocal_style.strip().lower() != "auto":
        style_note = (
            f"\n- The vocal performance is: {vocal_style.strip()}. "
            "Write the lyrics to match that performance (e.g. duet = two voiced "
            "parts, choir = anthemic unison lines, whispery = short intimate lines)."
        )
    system = (
        "You are an accomplished songwriter. Write original, singable lyrics.\n"
        "Rules:\n"
        f"- Use structure tags on their own lines: [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Bridge], [Outro]. Follow structure {structure}.\n"
        "- Show, don't tell: concrete images over stated feelings.\n"
        "- Short lines (4-9 syllables); match syllable counts across parallel lines.\n"
        "- End the chorus with the strongest, most repeatable hook line.\n"
        "- No clichés, no forced rhymes, no artist names, no song titles.\n"
        f"- 16-28 lines total. Output lyrics only — no commentary.{style_note}"
    )
    user = f'Write a song.\nTitle: "{title}"\nGenre/style: {genre}\nMood/theme: {mood}'
    return chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=4096,
        temperature=0.8,
    )


def write_cover_prompt(title: str, genre: str, mood: str, lyrics: str) -> str:
    """Image-generation prompt for the track's cover art."""
    system = (
        "You write image-generation prompts for album cover art. Rules:\n"
        "- One evocative paragraph (max 70 words) describing a striking, printable album cover.\n"
        "- Include art style, colour palette, lighting, and composition; tie the imagery to the song's mood and theme.\n"
        "- Do NOT ask for text, words, letters, or logos in the image.\n"
        "- Do not mention the title inside the prompt.\n"
        "Output the prompt only."
    )
    user = (
        f"Song title: {title}\nGenre/style: {genre}\nMood/theme: {mood}\n"
        f"Excerpt of lyrics:\n{lyrics[:600]}"
    )
    return chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=2048,
        temperature=0.8,
    )


def write_dj_script(previous_title: str | None, previous_genre: str | None,
                    next_title: str, next_genre: str) -> str:
    """Short radio-DJ transition script (spoken aloud by the TTS service)."""
    if previous_title:
        user = (
            f"You host an AI jukebox radio show. We just played \"{previous_title}\" "
            f"({previous_genre}). Transition to the next track \"{next_title}\" ({next_genre}) "
            "in 2-4 sentences (max 55 words), with one witty link between the two. "
            "Energetic, natural spoken language — no hashtags, emojis, or stage directions."
        )
    else:
        user = (
            f"You host an AI jukebox radio show. Open the show and introduce the first "
            f"track \"{next_title}\" ({next_genre}). 2-4 sentences (max 55 words), energetic "
            "and natural — no hashtags, emojis, or stage directions."
        )
    return chat([{"role": "user", "content": user}], max_tokens=1024, temperature=0.8)
