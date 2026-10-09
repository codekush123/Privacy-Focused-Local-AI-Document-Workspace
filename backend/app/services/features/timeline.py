"""Timeline: every dated event in the selected documents, verified and sorted.

The model proposes the events as schema-constrained JSON: the date, the date
as written, a title, one sentence, a short quote from the source and where the
quote is (source number and section). The app then checks each event: the date
must appear - in any common English or Finnish form ("14 August 2026",
"14.8.2026", "2026-08-14", "elokuussa 2026") - in the same paragraph or table
row as the event's own words, in the cited section. A date that is on the page
but belongs to something else does not count. If the cited section does not
hold it, the app looks for the paragraph that does in the same document.
Events are sorted by the app, never by the model, and unverified events are
kept but flagged, so nothing is hidden from the user.
"""
from __future__ import annotations

import calendar
import re
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentContent

from .citations import Citation, extract_citations
from .structured import ask_structured

# On a CPU the model writes about 6 tokens per second, so the timeline is kept short
# enough to finish in a few minutes; the limit is also enforced by the JSON schema.
MAX_EVENTS = 15

EN_MONTHS = [m.lower() for m in calendar.month_name[1:]]
# Finnish month names share a stem across cases: "elokuu", "elokuuta", "elokuussa".
FI_MONTH_STEMS = ["tammikuu", "helmikuu", "maaliskuu", "huhtikuu", "toukokuu", "kesäkuu",
                  "heinäkuu", "elokuu", "syyskuu", "lokakuu", "marraskuu", "joulukuu"]


class TimelineEventSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str = Field(description="The date as ISO: YYYY-MM-DD, or YYYY-MM if only the month is known, or YYYY")
    date_text: str = Field(description="The date exactly as it is written in the source, e.g. '14 August 2026' or '14.8.2026'")
    title: str = Field(description="What happened or is planned, at most 6 words")
    detail: str = Field(description="One short sentence, at most 15 words")
    quote: str = Field(description="The words of the source around the date, copied exactly, at most 12 words")
    source_document: int = Field(description="Number of the source the date is taken from: the N in <source id=\"N\">")
    source_location: str = Field(description="Section of that source, exactly as its heading: e.g. Page 4, Slide 2, "
                                             "Sheet: Sites, Heading: Decisions")


class TimelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[TimelineEventSpec] = Field(max_length=MAX_EVENTS)


class TimelineEvent(BaseModel):
    date: str  # normalised ISO, at the precision the source gives
    precision: Literal["day", "month", "year"]
    date_text: str
    title: str
    detail: str
    source: str
    citation: Citation | None = None
    document_name: str | None = None
    status: Literal["verified", "date_elsewhere", "date_not_in_source", "citation_unresolved", "invalid_date"]


class TimelineResult(BaseModel):
    events: list[TimelineEvent]
    counts: dict[str, int]
    documents: list[str]


INSTRUCTIONS = """List the dated events in the selected source materials: things that happened or are planned on a specific day, month or year - for example meetings, deadlines, decisions, commissioning dates, incidents, launches and closures.

Rules:
- Use only dates that are written in the sources. Do not calculate or guess dates.
- One event per date and topic; do not repeat the same event from several sources.
- At most {max_events} events, the most important ones first.
- For each event give the source number and section where the date is written, and copy the words around the date exactly.
- Write the title and the sentence in {language}."""


def _parse_iso(value: str) -> tuple[int, int | None, int | None] | None:
    m = re.fullmatch(r"\s*(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?\s*", value or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2) and int(m.group(2)), m.group(3) and int(m.group(3))
    try:
        if d:
            Date(y, mo, d)
        elif mo and not 1 <= mo <= 12:
            return None
    except ValueError:
        return None
    return y, mo or None, d or None


def _parse_text(text: str) -> tuple[int, int | None, int | None] | None:
    """Fallback: read a date written in English or Finnish."""
    t = text.lower()
    if m := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        return _parse_iso(m.group(0))
    if m := re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b", t):
        return _parse_iso(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
    year = re.search(r"\b(1[89]\d{2}|20\d{2})\b", t)
    if not year:
        return None
    month = next((i + 1 for i, name in enumerate(EN_MONTHS) if name in t), None) or \
        next((i + 1 for i, stem in enumerate(FI_MONTH_STEMS) if stem in t), None)
    day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th|\.)?\s+(?:of\s+)?[a-zåäö]", t) if month else None
    return _parse_iso(f"{year.group(1)}" + (f"-{month}" if month else "") + (f"-{day.group(1)}" if day else ""))


def date_forms(y: int, mo: int | None, d: int | None) -> list[str]:
    """Ways the same date is commonly written in English and Finnish (lower case)."""
    if mo is None:
        return [str(y)]
    en, fi = EN_MONTHS[mo - 1], FI_MONTH_STEMS[mo - 1]
    if d is None:
        return [f"{en} {y}", f"{y}-{mo:02d}", f"{mo}/{y}", f"{fi}"]  # Finnish: "toukokuussa 2025"
    return [f"{d}.{mo}.{y}", f"{d}. {mo}. {y}", f"{y}-{mo:02d}-{d:02d}", f"{d} {en} {y}", f"{en} {d}, {y}",
            f"{d}. {fi}", f"{d} {en}"]


# Words that say nothing about which event a date belongs to.
_GENERIC = {"vuonna", "vuoden", "year", "years", "month", "planned", "expected", "will", "with", "from", "that",
            "this", "kuluessa", "mennessä", "alussa", "lopussa", "aikana", "during", "beginning", "end",
            "date", "päivä", "päivämäärä", "aika"}
# A paragraph or table row this short is about one thing, so one shared word is enough.
SHORT_UNIT = 160
# Share of the quote's content words that must be in the paragraph holding the date.
QUOTE_SHARE = 0.6


def _stems(*texts: str) -> set[str]:
    """Content-word stems (first 5 letters), so Finnish case endings still match."""
    out = set()
    for text in texts:
        for w in re.findall(r"[^\W\d_]{4,}", text.lower()):
            if w in _GENERIC or w in EN_MONTHS or any(w.startswith(m) for m in FI_MONTH_STEMS):
                continue
            out.add(w[:5])
    return out


def _units(markdown: str) -> list[str]:
    """Paragraphs, with every table row as its own unit."""
    units: list[str] = []
    for block in re.split(r"\n\s*\n", markdown):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if lines and all(ln.lstrip().startswith("|") for ln in lines):
            units.extend(lines)
        elif lines:
            units.append(" ".join(lines))
    return units


def _has_date(unit: str, date_text: str, parsed: tuple[int, int | None, int | None]) -> bool:
    hay = re.sub(r"\s+", " ", unit.lower())
    written = re.sub(r"\s+", " ", date_text.lower().strip())
    if len(written) >= 4 and written in hay:
        return True
    y, mo, d = parsed
    if mo is None:
        return re.search(rf"(?<!\d){y}(?!\d)", hay) is not None
    if str(y) not in hay and not (d and f"{d}.{mo}." in hay):
        return False
    return any(form in hay for form in date_forms(y, mo, d))


def date_beside_event(markdown: str, event: "TimelineEventSpec", parsed: tuple[int, int | None, int | None],
                      heading: str = "") -> str:
    """'beside' when the date is in a paragraph (or table row) that also names the
    event; 'elsewhere' when the date is in the text but not beside the event; '' when absent.

    The quote the model copied is the strongest evidence: when it has at least
    three content words, the paragraph must contain most of them. (Seen with the
    real model: "Kivijärvi solar park completed in 2025" shared only the generic
    words "solar park" and "completed" with a 2025 paragraph about another park.)
    Without a usable quote, words of the event's title and sentence must appear
    in the paragraph or its section heading - two in a long paragraph, one in a
    short one, which is about a single thing anyway.
    """
    quote = _stems(event.quote)
    words = _stems(event.quote, event.title, event.detail)
    context = _stems(heading)
    found = False
    for unit in _units(markdown):
        if not _has_date(unit, event.date_text, parsed):
            continue
        found = True
        present = _stems(unit) | context
        if len(quote) >= 3:
            if len(quote & present) >= QUOTE_SHARE * len(quote):
                return "beside"
            continue
        need = 1 if len(unit) <= SHORT_UNIT else min(2, len(words)) or 1
        if len(words & present) >= need:
            return "beside"
    return "elsewhere" if found else ""


def _relocate(event: "TimelineEventSpec", parsed, documents: list[DocumentContent], order: list[int]) -> Citation | None:
    """Citation of the first section (in the given document order) holding the date beside the event."""
    for index in order:
        for sec in documents[index - 1].sections:
            if date_beside_event(sec.markdown, event, parsed, sec.title) == "beside":
                found = extract_citations(f"[S{index}: {sec.locator}]", documents)
                if found and found[0].found:
                    return found[0]
    return None


def verify_events(spec: TimelineSpec, documents: list[DocumentContent]) -> TimelineResult:
    events: list[TimelineEvent] = []
    seen: set[tuple[str, str]] = set()
    for e in spec.events[:MAX_EVENTS]:
        parsed = _parse_iso(e.date) or _parse_text(e.date_text)
        marker = f"[S{e.source_document}: {e.source_location.strip()}]"
        cites = extract_citations(marker, documents)
        cite = cites[0] if cites and cites[0].found else None
        if parsed is None:
            iso, precision, status = e.date.strip(), "year", "invalid_date"
        else:
            y, mo, d = parsed
            iso = f"{y}" + (f"-{mo:02d}" if mo else "") + (f"-{d:02d}" if d else "")
            precision = "day" if d else "month" if mo else "year"
            status = "citation_unresolved"
            if cite is not None:
                doc = next(x for x in documents if x.id == cite.document_id)
                section = next(sec for sec in doc.sections if sec.section_id == cite.section_id)
                where = date_beside_event(section.markdown, e, parsed, section.title)
                status = "verified" if where == "beside" else "date_elsewhere" if where else "date_not_in_source"
            if status != "verified":
                # The cited location may be wrong although the date is real: look for
                # the paragraph that holds it in the named document. Only when the
                # source number names no document at all (seen: the model wrote the
                # page number there) are all selected documents searched - a wider
                # search finds more same-year mentions of the same site that belong
                # to other events.
                valid = 1 <= e.source_document <= len(documents)
                order = [e.source_document] if valid else list(range(1, len(documents) + 1))
                relocated = _relocate(e, parsed, documents, order)
                if relocated is not None:
                    cite, status = relocated, "verified"
        key = (iso, e.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        events.append(TimelineEvent(
            date=iso, precision=precision, date_text=e.date_text.strip(), title=e.title.strip(),
            detail=e.detail.strip(), source=cite.marker if cite else marker, citation=cite,
            document_name=cite.document_name if cite else None, status=status,
        ))
    # The app sorts; a year-only event comes before the months of that year.
    # ("-" sorts before digits, so "2026---" < "2026-05" < "2026-05-14".)
    events.sort(key=lambda ev: (ev.status == "invalid_date", ev.date.ljust(10, "-")))
    counts: dict[str, int] = {"total": len(events)}
    for ev in events:
        counts[ev.status] = counts.get(ev.status, 0) + 1
    return TimelineResult(events=events, counts=counts, documents=[d.display_name for d in documents])


async def build_timeline(documents: list[DocumentContent], language: str | None = None) -> TimelineResult:
    spec = await ask_structured(
        TimelineSpec,
        INSTRUCTIONS.format(max_events=MAX_EVENTS, language=language or "the language of the documents"),
        documents,
        what="timeline",
        max_tokens=2600,
    )
    return verify_events(spec, documents)
