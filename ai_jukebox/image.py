"""Client for the class FLUX image service (port 9006 — vLLM-Omni).

OpenAI-compatible images/generations endpoint; the response carries the
image as base64 (b64_json). Verified against the live service.
"""
from __future__ import annotations

import base64

from . import config, http


def generate_cover(prompt: str, size: str = "1024x1024", timeout: int = 300) -> dict:
    """Render cover art from a text prompt.

    Returns {"image": <PNG bytes>, "revised_prompt": <str or "">}.
    """
    payload = {
        "model": config.IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    data = http.post_json(
        f"{config.base_url(config.IMAGE_PORT)}/v1/images/generations",
        payload,
        timeout=timeout,
    )
    try:
        item = data["data"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise http.ServiceError(f"Unexpected image response: {str(data)[:300]}") from e

    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        raw = http.get_raw(item["url"], timeout=timeout)
    else:
        raise http.ServiceError(f"Image response had no b64_json/url: {str(item)[:300]}")
    if not raw:
        raise http.ServiceError("Image service returned empty bytes.")
    return {"image": raw, "revised_prompt": item.get("revised_prompt", "") or ""}
