"""Filename and path safety helpers."""
from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path

# Letters of every script are kept: the name is shown to the user and the
# model, and "pöytäkirja.docx" must not become "p_yt_kirja.docx". Uploads are
# stored under a server-generated id; this name never forms a path on its own.
# Removed: what Windows forbids in a file name, and control and format
# characters - the latter include invisible right-to-left overrides that can
# disguise an extension ("report[U+202E]fdp.exe" displays as "reportexe.pdf").
_FORBIDDEN = set('<>:"/\\|?*')
# Names Windows refuses for a file, whatever the extension.
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _clean(ch: str) -> str:
    category = unicodedata.category(ch)
    if ch in _FORBIDDEN or category[0] == "C":
        return "\x00"  # marks an unsafe run, collapsed to one underscore below
    return " " if category[0] == "Z" else ch  # no-break and other exotic spaces


def sanitize_filename(name: str, default: str = "file") -> str:
    """Return a filesystem-safe base name (no directories, no control chars)."""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"\x00+", "_", "".join(_clean(ch) for ch in name)).strip(". ")
    if name.split(".")[0].lower() in _WINDOWS_RESERVED:
        name = "_" + name
    if not name:
        name = default
    return name[:150]


def new_id() -> str:
    return uuid.uuid4().hex


def safe_child(base: Path, name: str) -> Path:
    """Join ``name`` onto ``base`` and refuse anything that escapes ``base``."""
    candidate = (base / name).resolve()
    if base.resolve() not in candidate.parents and candidate != base.resolve():
        raise ValueError("Invalid path")
    return candidate


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")
