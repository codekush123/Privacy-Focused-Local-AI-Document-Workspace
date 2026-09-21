"""Logging setup.

Logs deliberately contain only file names, types, timings, token counts and
errors. Full document contents are never logged.
"""
from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
