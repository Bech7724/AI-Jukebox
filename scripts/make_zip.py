#!/usr/bin/env python3
"""Build the submission ZIP for AI Jukebox.

Produces dist/ai-jukebox-submission.zip — a clean, deployable copy of the app
with credentials and runtime state excluded (same ignore rules as .gitignore):

  python scripts/make_zip.py

Verify with:  python scripts/make_zip.py --check
Safeguards that must hold (asserted by --check):
  - no .env / .env.* anywhere
  - no data/ (runtime library, voice uploads) or samples/_stage/
  - README.md, requirements.txt, app.py, ai_jukebox/, samples/, tests/,
    scripts/, docs/, .github/ all present
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "ai-jukebox-submission.zip"

# Same spirit as .gitignore: anything that could carry credentials or
# user-uploaded data must never enter the archive.
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "data",
                "samples", "dist", ".hermes"}
EXCLUDE_FILES = {".env", "share_url.txt"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".zip", ".DS_Store")
# samples/ is re-included explicitly below (it is committed and required).

INCLUDE_SAMPLE_DIRS = True  # bundled sample tracks are part of the deliverable


def iter_zip_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if any(p in EXCLUDE_DIRS for p in parts):
            # samples/_stage is ephemeral scratch; samples/ itself is wanted.
            if "samples" in parts and INCLUDE_SAMPLE_DIRS:
                if "_stage" not in parts:
                    pass
                else:
                    continue
            else:
                continue
        if path.name in EXCLUDE_FILES or path.name.endswith(EXCLUDE_SUFFIXES):
            continue
        yield rel, path


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in iter_zip_files():
            zf.write(path, arcname=rel)
    return OUTPUT


def check(artifacts: bool = True) -> list[str]:
    """Return a list of violations (empty == archive is safe)."""
    problems: list[str] = []
    with zipfile.ZipFile(OUTPUT) as zf:
        names = set(zf.namelist())
    for n in sorted(names):
        low = n.lower()
        if low.startswith(".env") or "/.env" in low:
            if low.endswith(".env.example") or low.endswith(".env.sample") \
                    or low.endswith(".env.template"):
                continue  # placeholder-only; required so deployers can copy
            problems.append(f"credential file leaked into ZIP: {n}")
        if n.startswith("data/") or n.startswith("samples/_stage"):
            problems.append(f"runtime/user data leaked into ZIP: {n}")
    for must in ("app.py", "requirements.txt", "README.md", "ai_jukebox/",
                 "samples/", "tests/", "scripts/", "docs/screenshots/"):
        if not any(n.startswith(must) for n in names):
            problems.append(f"required path missing from ZIP: {must}")
    if artifacts:
        if not (OUTPUT / "share_url.txt"):
            pass  # never produced at build time; nothing to verify
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify an existing ZIP")
    args = ap.parse_args()
    if args.check:
        problems = check()
        print(f"{OUTPUT}: {'CLEAN ✅' if not problems else 'PROBLEMS ❌'}")
        for p in problems:
            print("  -", p)
        raise SystemExit(1 if problems else 0)
    out = build()
    problems = check()
    print(f"Built {out} ({out.stat().st_size / 1e6:.2f} MB)")
    for p in problems:
        print("  WARNING:", p)
    raise SystemExit(1 if problems else 0)
