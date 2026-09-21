"""Plain-text style outputs: .txt, .md and .csv."""
from __future__ import annotations

import csv
from pathlib import Path

from app.schemas.artifacts import XlsxSpec


def write_text(text: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def write_csv(spec: XlsxSpec, out_path: Path) -> Path:
    """Write the first sheet of an XlsxSpec as UTF-8 CSV (Excel-friendly BOM)."""
    sheet = spec.sheets[0] if spec.sheets else None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        if sheet:
            if sheet.headers:
                w.writerow(sheet.headers)
            for r in sheet.rows:
                w.writerow(r)
    return out_path
