"""Shared pytest fixtures.

Tests use an isolated temporary data directory so they never touch the real
document library. Tests that need a running llama-server are skipped
automatically when it is not reachable.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES = TESTS_DIR / "fixtures"
PHRASE = "BLUE ELEPHANT 1947"
MULTILINGUAL = {
    "english": "English hello",
    "finnish": "Hyvää päivää",
    "chinese": "你好，世界",
    "arabic": "مرحبا بالعالم",
    "russian": "Привет, мир",
}

# Isolate the data directory before the app modules are imported.
_TMP_DATA = TESTS_DIR / "_tmp_data"
os.environ.setdefault("LDW_DATA_DIR", str(_TMP_DATA))


def pytest_sessionstart(session):
    if not (FIXTURES / "sample.docx").exists():
        subprocess.run([sys.executable, str(TESTS_DIR / "make_fixtures.py")], check=True)


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.document_store import document_store
    from app.services.export_store import export_store

    document_store.clear()
    export_store.clear()
    with TestClient(app) as c:
        yield c
    document_store.clear()
    export_store.clear()


def llama_server_available() -> bool:
    from app.config import settings

    try:
        return httpx.get(f"{settings.llm_base_url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


requires_llama = pytest.mark.skipif(
    not llama_server_available(), reason="llama-server is not running on the configured endpoint"
)


@pytest.fixture
def anyio_backend():
    """Run async tests on asyncio only (pytest-anyio would otherwise also try trio)."""
    return "asyncio"
