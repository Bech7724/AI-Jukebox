"""Central configuration for the AI Jukebox app.

Every AI feature rides on the class model services on the class network
(dobolyi.com — see class-endpoints.txt). Values can be overridden with
environment variables or a local .env file (see .env.example).

Port 9000 is reserved for agentic/Hermes use and is deliberately NEVER
used by this app.
"""
import os

from dotenv import load_dotenv

load_dotenv()

BASE_HOST = os.environ.get("AIJ_BASE_HOST", "http://dobolyi.com")
# Class key lives ONLY in the developer's local .env (gitignored) — never
# in this repo, docs, logs, or archives. See .env.example for the placeholder.
API_KEY = os.environ.get("AIJ_API_KEY", "")

# Service ports (documented in class-endpoints.txt)
LLM_PORT = os.environ.get("AIJ_LLM_PORT", "9001")        # Qwen3.6-35B text LLM (vLLM)
IMAGE_PORT = os.environ.get("AIJ_IMAGE_PORT", "9006")    # FLUX.2-klein cover art (vLLM-Omni)
MUSIC_PORT = os.environ.get("AIJ_MUSIC_PORT", "9007")    # ACE-Step 1.5 XL Turbo (async API)
TTS_PORT = os.environ.get("AIJ_TTS_PORT", "9008")        # Chatterbox Multilingual V3 (FastAPI wrapper)

# Model identifiers served by those ports
LLM_MODEL = os.environ.get("AIJ_LLM_MODEL", "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit")
IMAGE_MODEL = os.environ.get("AIJ_IMAGE_MODEL", "black-forest-labs/FLUX.2-klein-4B")
MUSIC_MODEL = os.environ.get("AIJ_MUSIC_MODEL", "acestep-v15-xl-turbo")  # None -> server default
TTS_MODEL = os.environ.get("AIJ_TTS_MODEL", "chatterbox-v3")

# Local artifact storage (generated music, cover art, DJ audio, index)
DATA_DIR = os.environ.get(
    "AIJ_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)


def base_url(port: str) -> str:
    """http://<host>:<port> for a class service."""
    return f"{BASE_HOST}:{port}"
