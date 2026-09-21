"""Privacy Guard: find personal data in a document and produce a redacted copy.

Detection combines two layers:
  * deterministic patterns for machine-readable identifiers (e-mail, phone,
    IBAN, credit card with Luhn check, Finnish personal identity code, IPv4)
  * the local model for context-dependent entities (person names, street
    addresses, organisations, dates of birth, other identifiers)

The user reviews every finding in the UI (keep / redact, custom replacement)
before anything is changed. Redaction replaces each occurrence with a
consistent placeholder such as [PERSON-1] so the text stays readable, and the
redacted copy can be exported or added to the library so the user can chat
with an anonymised version of the document.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentContent

from .structured import ask_structured

Category = Literal[
    "person", "email", "phone", "address", "organization", "id_number", "iban", "credit_card", "date_of_birth", "ip_address", "other"
]


class Finding(BaseModel):
    text: str
    category: Category
    count: int = 1
    detected_by: Literal["pattern", "ai"]
    reason: str = ""
    context: str = ""  # short snippet around the first occurrence


class AiFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="The exact text as it appears in the document")
    category: Category
    reason: str = Field(default="", description="Why this is personal data, a few words")


class AiFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[AiFinding]


class ScanResult(BaseModel):
    document_id: str
    document_name: str
    findings: list[Finding]
    ai_used: bool
    ai_error: str | None = None


class RedactionItem(BaseModel):
    text: str
    category: Category
    replacement: str = ""  # empty = automatic placeholder


PATTERNS: list[tuple[Category, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("id_number", re.compile(r"\b\d{6}[-+A]\d{3}[0-9A-Z]\b")),  # Finnish henkilötunnus
    ("phone", re.compile(r"(?<![\w/])(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)\d{3}[\s-]?\d{2,4}(?:[\s-]?\d{2,4})?(?!\w)")),
    ("ip_address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
]

PLACEHOLDER = {
    "person": "PERSON", "email": "EMAIL", "phone": "PHONE", "address": "ADDRESS", "organization": "ORG",
    "id_number": "ID", "iban": "IBAN", "credit_card": "CARD", "date_of_birth": "DOB", "ip_address": "IP", "other": "REDACTED",
}


def _luhn(s: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", s)]
    if len(digits) < 13:
        return False
    total, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _snippet(text: str, needle: str, width: int = 40) -> str:
    i = text.find(needle)
    if i < 0:
        return ""
    start, end = max(0, i - width), min(len(text), i + len(needle) + width)
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")


def pattern_scan(text: str) -> list[Finding]:
    found: dict[str, Finding] = {}
    taken: list[tuple[int, int]] = []  # spans already claimed by an earlier (more specific) pattern
    for cat, rx in PATTERNS:
        for m in rx.finditer(text):
            val = m.group(0).strip()
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            if cat == "credit_card" and not _luhn(val):
                continue
            if cat == "phone" and len(re.sub(r"\D", "", val)) < 7:
                continue
            taken.append((m.start(), m.end()))
            key = val.lower()
            if key in found:
                found[key].count += 1
                continue
            found[key] = Finding(text=val, category=cat, detected_by="pattern", reason="matches pattern", context=_snippet(text, val))
    return list(found.values())


AI_INSTRUCTIONS = """Find personal data in the selected source material that could identify a real, private person. Use these categories:
- person: full names of people (e.g. "Anna Petrova")
- address: street or home addresses
- organization: an employer or school named together with a specific person
- date_of_birth: birth dates
- id_number: student numbers, customer numbers, national IDs, passport numbers (e.g. "S001")
- email, phone, iban, credit_card, ip_address: if they appear
- other: only for identifiers that fit none of the above

NOT personal data (do not list): country or city names on their own, course codes, product names, job titles, technical terms, famous historical figures mentioned as subject matter, numbers that are scores or amounts.
Copy each item EXACTLY as it appears in the text. Return an empty list if there is none."""


async def scan_document(doc: DocumentContent, use_ai: bool = True) -> ScanResult:
    text = doc.full_markdown
    findings = pattern_scan(text)
    ai_error: str | None = None
    ai_used = False
    if use_ai:
        try:
            spec = await ask_structured(AiFindings, AI_INSTRUCTIONS, [doc], what="privacy scan", max_tokens=2000)
            ai_used = True
            known = {f.text.lower() for f in findings}
            for f in spec.findings:
                val = f.text.strip()
                if len(val) < 2 or val.lower() in known:
                    continue
                cat = f.category
                if cat == "other":  # models often fall back to 'other'; re-classify obvious cases
                    if re.fullmatch(r"[A-Z\u00C0-\u00DD][a-z\u00DF-\u00FF'-]+(?: [A-Z\u00C0-\u00DD][a-z\u00DF-\u00FF'-]+){1,3}", val):
                        cat = "person"
                    elif re.fullmatch(r"[A-Z]{0,3}-?\d{2,}[A-Z]?", val):
                        cat = "id_number"
                    elif len(val.split()) == 1 and val[:1].isupper():
                        continue  # single capitalised word (country, city, subject) - not PII
                f.category = cat
                if val not in text:
                    # tolerate case differences; skip hallucinated items
                    m = re.search(re.escape(val), text, re.I)
                    if not m:
                        continue
                    val = m.group(0)
                cnt = len(re.findall(re.escape(val), text))
                findings.append(Finding(text=val, category=f.category, count=cnt, detected_by="ai", reason=f.reason, context=_snippet(text, val)))
                known.add(val.lower())
        except Exception as exc:  # noqa: BLE001 - pattern results are still useful
            ai_error = str(exc)
    findings.sort(key=lambda f: (f.category, -f.count))
    return ScanResult(document_id=doc.id, document_name=doc.display_name, findings=findings, ai_used=ai_used, ai_error=ai_error)


def redact_text(text: str, items: list[RedactionItem]) -> tuple[str, dict[str, str]]:
    """Replace every occurrence of each item with a consistent placeholder. Returns (text, mapping)."""
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    # longest first so "Anna Petrova" is replaced before "Anna"
    for item in sorted(items, key=lambda i: len(i.text), reverse=True):
        if not item.text.strip():
            continue
        if item.replacement.strip():
            repl = item.replacement.strip()
        else:
            base = PLACEHOLDER.get(item.category, "REDACTED")
            counters[base] = counters.get(base, 0) + 1
            repl = f"[{base}-{counters[base]}]"
        mapping[item.text] = repl
        text = re.sub(re.escape(item.text), repl, text, flags=re.I)
    return text, mapping
