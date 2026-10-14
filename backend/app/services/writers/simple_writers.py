"""Plain-text style outputs: .txt, .md and .csv."""
from __future__ import annotations

import csv
from pathlib import Path

from app.schemas.artifacts import XlsxSpec
from app.utils.numbers import parse_number

# Excel treats a CSV cell that starts with one of these as a formula. Text from
# the model or a document must not become one ("=HYPERLINK(...)" can send data
# away when the file is opened), so such a cell is prefixed with an apostrophe,
# the usual way to mark text in a spreadsheet. Plain numbers such as -5 are kept.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_START) and parse_number(text) is None:
        return "'" + text
    return text


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
                w.writerow([csv_safe(h) for h in sheet.headers])
            for r in sheet.rows:
                w.writerow([csv_safe(v) for v in r])
    return out_path
