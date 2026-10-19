"""Tiny authenticated HTTP helpers shared by every class-service client.

Uses only the Python stdlib (urllib) so the app stays dependency-light.
All class services authenticate with the same shared key.
"""
import json
import urllib.error
import urllib.request

from . import config


class ServiceError(RuntimeError):
    """Raised when a class service rejects, misbehaves, or is unreachable."""


def _headers() -> dict:
    if not config.API_KEY:
        raise ServiceError(
            "AIJ_API_KEY is not set. Copy .env.example to .env and fill in the "
            "class-service key from class-endpoints.txt (never commit it)."
        )
    return {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json",
    }


def _open(req: urllib.request.Request, timeout: int):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        raise ServiceError(f"HTTP {e.code} from {e.url}: {detail}") from e
    except urllib.error.URLError as e:
        raise ServiceError(f"Cannot reach {req.full_url}: {e.reason}") from e


def post_json(url: str, payload: dict, timeout: int = 120) -> dict:
    """POST a JSON payload and parse the JSON response."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=_headers(), method="POST"
    )
    status, body = _open(req, timeout)
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ServiceError(f"Non-JSON response ({status}) from {url}: {body[:200]}") from e


def post_raw(url: str, payload: dict, timeout: int = 300) -> bytes:
    """POST a JSON payload and return the raw body (audio bytes, etc.)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=_headers(), method="POST"
    )
    _, body = _open(req, timeout)
    return body


def get_raw(url: str, timeout: int = 300) -> bytes:
    """GET a URL with the shared key and return the raw body."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {config.API_KEY}"})
    _, body = _open(req, timeout)
    return body
