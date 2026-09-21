"""Explicit, user-triggered web URL import.

This is the only normal operation of the prototype that contacts the network.
Safety measures:
  * only http:// and https:// are accepted
  * private / loopback / link-local targets are rejected (basic SSRF protection)
  * request timeout and maximum response size are enforced
  * redirects are followed but re-validated against the same rules
  * no linked pages are crawled
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models.document import DocumentContent, SourceType
from app.utils.files import new_id

from .base import ParseError, make_section
from .html_parser import html_to_markdown

USER_AGENT = "LocalDocumentWorkspace/0.1 (+prototype; local processing)"


class UrlRejected(ParseError):
    pass


def _reject_private_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlRejected(f"The host '{host}' could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise UrlRejected("URLs pointing to local or private network addresses are not allowed.")


def validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlRejected("Only http:// and https:// URLs are supported.")
    if not parsed.netloc or not parsed.hostname:
        raise UrlRejected("The URL is malformed.")
    if parsed.username or parsed.password:
        raise UrlRejected("URLs with embedded credentials are not allowed.")
    host = parsed.hostname
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".localhost"):
        raise UrlRejected("URLs pointing to local or private network addresses are not allowed.")
    _reject_private_host(host)
    return url


async def fetch_url_document(url: str) -> DocumentContent:
    url = validate_url(url)
    max_bytes = settings.url_max_bytes
    try:
        async with httpx.AsyncClient(
            timeout=settings.url_fetch_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5"},
        ) as client:
            current = url
            for _ in range(5):
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = validate_url(str(resp.url.join(resp.headers["location"])))
                        continue
                    if resp.status_code >= 400:
                        raise ParseError(f"The website responded with HTTP {resp.status_code}.")
                    ctype = resp.headers.get("content-type", "").lower()
                    length = resp.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise ParseError(f"The page is larger than the allowed {max_bytes // (1024 * 1024)} MB.")
                    chunks = bytearray()
                    async for part in resp.aiter_bytes():
                        chunks.extend(part)
                        if len(chunks) > max_bytes:
                            raise ParseError(f"The page is larger than the allowed {max_bytes // (1024 * 1024)} MB.")
                    encoding = resp.encoding or "utf-8"
                    break
            else:
                raise ParseError("Too many redirects.")
    except httpx.TimeoutException as exc:
        raise ParseError("The website did not respond in time.") from exc
    except httpx.HTTPError as exc:
        raise ParseError(f"The URL could not be fetched: {exc}") from exc

    try:
        body = bytes(chunks).decode(encoding, errors="replace")
    except LookupError:
        body = bytes(chunks).decode("utf-8", errors="replace")

    if "html" in ctype or body.lstrip()[:200].lower().startswith(("<!doctype", "<html")):
        title, text = html_to_markdown(body)
    else:
        title, text = "", body
    if not text.strip():
        raise ParseError("No readable content was found at that URL.")
    display = title or current
    doc = DocumentContent(
        id=new_id(),
        original_filename=current,
        source_type=SourceType.url,
        display_name=display,
        source_path=None,
        sections=[make_section(1, display, f"Web page: {current}", text, url=current, page_title=title)],
        size_bytes=len(chunks),
        metadata={"url": current, "content_type": ctype, "network_used": True},
    )
    return doc.finalize()
