"""Local document store.

Uploaded originals go to ``data/uploads/<id>.<ext>``; the normalized
``DocumentContent`` is persisted as JSON in ``data/converted/<id>.json`` so the
library survives backend restarts. Deleting a document removes both files.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from app.config import settings
from app.models.document import DocumentContent, DocumentSummary
from app.services.parsers import ParseError, parse_file, parse_pasted_text
from app.services.parsers.url_fetcher import fetch_url_document
from app.utils.files import extension_of, new_id, safe_child, sanitize_filename

log = logging.getLogger(__name__)


class DocumentStore:
    def __init__(self) -> None:
        self._docs: dict[str, DocumentContent] = {}
        self._lock = threading.Lock()
        settings.ensure_dirs()
        self._load()

    # ---------------------------------------------------------------- persist
    def _load(self) -> None:
        for f in settings.converted_dir.glob("*.json"):
            try:
                doc = DocumentContent.model_validate_json(f.read_text(encoding="utf-8"))
                self._docs[doc.id] = doc
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not load converted document %s: %s", f.name, exc)
        log.info("Document store loaded: %d document(s)", len(self._docs))

    def _save(self, doc: DocumentContent) -> None:
        path = safe_child(settings.converted_dir, f"{doc.id}.json")
        path.write_text(doc.model_dump_json(indent=None), encoding="utf-8")

    # ----------------------------------------------------------------- import
    def add_upload(self, original_filename: str, data: bytes) -> DocumentContent:
        safe_name = sanitize_filename(original_filename)
        ext = extension_of(safe_name)
        doc_id = new_id()
        target = safe_child(settings.uploads_dir, f"{doc_id}.{ext}" if ext else doc_id)
        target.write_bytes(data)
        t0 = time.perf_counter()
        try:
            doc = parse_file(target, safe_name)
        except ParseError:
            target.unlink(missing_ok=True)
            raise
        doc.id = doc_id
        doc.source_path = str(target)
        doc.size_bytes = len(data)
        self._commit(doc, t0)
        return doc

    def add_text(self, text: str, name: str | None = None) -> DocumentContent:
        doc_id = new_id()
        display = sanitize_filename(name or "Pasted text", default="Pasted text")
        target = safe_child(settings.uploads_dir, f"{doc_id}.txt")
        target.write_text(text, encoding="utf-8")
        t0 = time.perf_counter()
        doc = parse_pasted_text(target, display)
        doc.id = doc_id
        doc.source_path = str(target)
        self._commit(doc, t0)
        return doc

    async def add_url(self, url: str) -> DocumentContent:
        t0 = time.perf_counter()
        doc = await fetch_url_document(url)
        self._commit(doc, t0)
        return doc

    def _commit(self, doc: DocumentContent, t0: float) -> None:
        with self._lock:
            self._docs[doc.id] = doc
            self._save(doc)
        log.info(
            "Imported %s (%s): %d sections, %d chars in %.2fs",
            doc.display_name,
            doc.source_type.value,
            len(doc.sections),
            doc.character_count,
            time.perf_counter() - t0,
        )

    def save(self, doc: DocumentContent) -> DocumentContent:
        """Persist changes made to an existing document (e.g. merged figure descriptions)."""
        with self._lock:
            doc.character_count = len(doc.full_markdown)
            self._docs[doc.id] = doc
            self._save(doc)
        return doc

    def set_token_count(self, doc_id: str, tokens: int) -> None:
        with self._lock:
            doc = self._docs.get(doc_id)
            if doc:
                doc.token_count = tokens
                self._save(doc)

    # ------------------------------------------------------------------ query
    def list(self) -> list[DocumentSummary]:
        docs = sorted(self._docs.values(), key=lambda d: d.imported_at)
        return [DocumentSummary.from_document(d) for d in docs]

    def get(self, doc_id: str) -> DocumentContent | None:
        return self._docs.get(doc_id)

    def get_many(self, ids: list[str]) -> list[DocumentContent]:
        missing = [i for i in ids if i not in self._docs]
        if missing:
            raise KeyError(missing[0])
        return [self._docs[i] for i in ids]

    # ----------------------------------------------------------------- delete
    def delete(self, doc_id: str) -> bool:
        with self._lock:
            doc = self._docs.pop(doc_id, None)
        if doc is None:
            return False
        self._remove_files(doc)
        log.info("Deleted document %s (%s)", doc.display_name, doc.id)
        return True

    def clear(self) -> int:
        with self._lock:
            docs = list(self._docs.values())
            self._docs.clear()
        for d in docs:
            self._remove_files(d)
        log.info("Cleared %d document(s)", len(docs))
        return len(docs)

    @staticmethod
    def _remove_files(doc: DocumentContent) -> None:
        from app.services.vision.extractor import remove_images

        remove_images(doc.id)
        try:
            safe_child(settings.converted_dir, f"{doc.id}.json").unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
        if doc.source_path:
            p = Path(doc.source_path)
            try:
                if settings.uploads_dir.resolve() in p.resolve().parents:
                    p.unlink(missing_ok=True)
            except OSError:
                pass


document_store = DocumentStore()
