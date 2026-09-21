"""Filename and path safety helpers."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._\- ()\[\]]+")


def sanitize_filename(name: str, default: str = "file") -> str:
    """Return a filesystem-safe base name (no directories, no control chars)."""
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = _SAFE_CHARS.sub("_", name).strip(". ")
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
