"""Registry of generated files stored in ``data/exports``."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.config import settings
from app.utils.files import new_id, safe_child, sanitize_filename

log = logging.getLogger(__name__)


class ExportInfo(BaseModel):
    id: str
    filename: str
    kind: str  # docx | xlsx | pptx | csv | md | txt | pdf | tex
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources: list[str] = Field(default_factory=list)
    prompt: str = ""
    download_url: str = ""


class ExportStore:
    def __init__(self) -> None:
        settings.ensure_dirs()
        self._index_path = settings.exports_dir / "index.json"
        self._items: dict[str, ExportInfo] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            try:
                raw = json.loads(self._index_path.read_text(encoding="utf-8"))
                for item in raw:
                    info = ExportInfo.model_validate(item)
                    if self.path_for(info).exists():
                        self._items[info.id] = info
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not load export index: %s", exc)

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps([i.model_dump(mode="json") for i in self._items.values()], indent=1), encoding="utf-8"
        )

    def path_for(self, info: ExportInfo) -> Path:
        return safe_child(settings.exports_dir, f"{info.id}_{info.filename}")

    def reserve(self, filename: str, kind: str, sources: list[str], prompt: str) -> tuple[ExportInfo, Path]:
        info = ExportInfo(
            id=new_id(),
            filename=sanitize_filename(filename, default=f"export.{kind}"),
            kind=kind,
            size_bytes=0,
            sources=sources,
            prompt=prompt[:500],
        )
        info.download_url = f"/api/exports/{info.id}"
        return info, self.path_for(info)

    def commit(self, info: ExportInfo) -> ExportInfo:
        path = self.path_for(info)
        info.size_bytes = path.stat().st_size
        with self._lock:
            self._items[info.id] = info
            self._save()
        log.info("Export created: %s (%s, %d bytes)", info.filename, info.kind, info.size_bytes)
        return info

    def list(self) -> list[ExportInfo]:
        return sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)

    def get(self, export_id: str) -> ExportInfo | None:
        return self._items.get(export_id)

    def delete(self, export_id: str) -> bool:
        with self._lock:
            info = self._items.pop(export_id, None)
            if info is None:
                return False
            self.path_for(info).unlink(missing_ok=True)
            self._save()
        return True

    def clear(self) -> int:
        with self._lock:
            items = list(self._items.values())
            self._items.clear()
            for info in items:
                self.path_for(info).unlink(missing_ok=True)
            self._save()
        return len(items)


export_store = ExportStore()
