"""Privacy policy enforcement and status reporting.

Default mode is LOCAL ONLY: the LLM endpoint must be a loopback address, no
cloud AI APIs are configured, no analytics/telemetry exist, and all parsing,
inference and file generation happen on this machine. The only operation that
touches the network is the explicit web URL import.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from pydantic import BaseModel

from app.config import settings

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class PrivacyViolation(Exception):
    pass


def is_localhost_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
    except ValueError:
        return False
    if host.lower() in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_llm_endpoint_allowed(url: str | None = None) -> None:
    url = url or settings.llm_base_url
    if settings.local_only and not is_localhost_url(url):
        raise PrivacyViolation(
            f"LOCAL ONLY mode is enabled but the LLM endpoint '{url}' is not a localhost address. "
            "AI requests are blocked. Point LDW_LLM_BASE_URL at a local llama-server or disable local-only mode."
        )


class PrivacyStatus(BaseModel):
    mode: str
    local_only: bool
    llm_runtime: str = "llama-server (llama.cpp)"
    llm_endpoint: str
    llm_endpoint_is_local: bool
    ai_requests_allowed: bool
    cloud_ai_apis: bool = False
    analytics: bool = False
    telemetry: bool = False
    documents_leave_machine: bool = False
    network_needed: str
    data_dir: str
    notes: list[str]


def privacy_status() -> PrivacyStatus:
    local = is_localhost_url(settings.llm_base_url)
    allowed = local or not settings.local_only
    notes = [
        "All document parsing happens locally.",
        "All generated files are written to the local data directory.",
        "Uploaded files never leave this machine.",
        "Web URL import is the only operation that contacts the network, and only after you explicitly request it.",
    ]
    if settings.local_only and not local:
        notes.insert(0, "WARNING: the configured LLM endpoint is not localhost - AI requests are blocked.")
    if not settings.local_only:
        notes.insert(0, "Local-only mode is DISABLED: the LLM endpoint may be remote. Documents may leave this machine.")
    return PrivacyStatus(
        mode="LOCAL ONLY" if settings.local_only else "REMOTE ALLOWED",
        local_only=settings.local_only,
        llm_endpoint=settings.llm_base_url,
        llm_endpoint_is_local=local,
        ai_requests_allowed=allowed,
        documents_leave_machine=not local,
        network_needed="No (URL import only)",
        data_dir=str(settings.data_dir),
        notes=notes,
    )
