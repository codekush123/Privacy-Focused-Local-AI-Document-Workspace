"""Deterministic scoring of benchmark answers.

No second model judges the answers: every rule here is a plain text check, so
the same answer always gets the same score and anyone can audit why.

Answer patterns (used in questions.json) come in three forms:

``"num:184.6"``  a number; matches 184.6, 184,6 (Finnish), and grouped forms
                 such as 1,148 / 1 148 for 1148
``"re:..."``     a case-insensitive regular expression
``"text"``       a case-insensitive substring (used for name stems such as
                 "pohjanka", which matches Pohjankangas and Pohjankankaan)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models.document import DocumentContent
from app.services.features.citations import Citation, extract_citations

# ------------------------------------------------------------------ numbers

# A number, optionally with thousands groups (1,148 / 1 148 / 1.148) and decimals.
_NUMBER = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[   ,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w])"
)
_CITATION_MARKER = re.compile(r"\[S\d+[^\]]{0,100}\]")
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
_THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)


def number_values(token: str) -> set[float]:
    """Every value a written number can mean. "1,148" is 1148 in English but
    1.148 in Finnish, so both are returned; the context decides nothing here."""
    t = token.replace(" ", " ").replace(" ", " ")
    values: set[float] = set()
    if " " in t:
        head, _, tail = t.replace(" ", "").partition(",")
        try:
            values.add(float(head + ("." + tail if tail else "")))
        except ValueError:
            pass
        return values
    seps = [c for c in t if c in ",."]
    if not seps:
        return {float(t)}
    if len(seps) == 1:
        whole, frac = re.split(r"[.,]", t)
        values.add(float(f"{whole}.{frac}"))  # decimal reading
        if len(frac) == 3:
            values.add(float(whole + frac))  # thousands-separator reading
        return values
    # Several separators: the last one is the decimal mark if it differs.
    last = seps[-1]
    if all(s == last for s in seps):
        values.add(float(re.sub(r"[.,]", "", t)))
    else:
        whole, frac = t.rsplit(last, 1)
        values.add(float(re.sub(r"[.,]", "", whole) + "." + frac))
    return values


def numbers_in(text: str) -> list[tuple[str, set[float]]]:
    return [(m.group(1), number_values(m.group(1))) for m in _NUMBER.finditer(text)]


def _close(a: float, b: float) -> bool:
    return abs(a - b) < 1e-6 * max(1.0, abs(a), abs(b))


# ---------------------------------------------------------------- patterns

def matches(pattern: str, text: str) -> bool:
    if pattern.startswith("num:"):
        want = float(pattern[4:])
        return any(_close(v, want) for _tok, vals in numbers_in(text) for v in vals)
    if pattern.startswith("re:"):
        return re.search(pattern[3:], text, re.IGNORECASE) is not None
    return pattern.casefold() in text.casefold()


def matches_any(patterns: list[str], text: str) -> bool:
    return any(matches(p, text) for p in patterns)


# --------------------------------------------------------------- abstention

# "The documents do not mention ..." in its many shapes, English and Finnish.
_ABSTAIN = [re.compile(p, re.IGNORECASE) for p in (
    # "not" and its contractions: "do not", "don't", "doesn't", "isn't"
    r"(?:\bnot\b|n't\b)[^.\n]{0,60}\b(mention\w*|provide\w*|specif\w*|state\w*|given|available|include\w*|list\w*|found|"
    r"contain\w*|report\w*|disclose\w*|cover\w*|present\w*|identif\w*|name\w*|refer\w*|discuss\w*|appear\w*|"
    r"say|says|said|give|gives|show\w*)",
    r"\bno\s+(information|mention|data|details?|record)\b",
    r"\b(cannot|can't|could not|couldn't|unable to)\b[^.\n]{0,40}\b(find|determine|answer|locate|identify)",
    r"\bnone of the (documents|sources)\b",
    r"\bei(vät)?\b[^.\n]{0,60}\b(mainit\w*|kerro\w*|kerrota|löyd\w*|löyt\w*|ilmene\w*|ilmoit\w*|anneta|esitetä|esitet\w*|"
    r"sisäll\w*|kata|määrit\w*|raportoi\w*|tietoa)",
    r"\b(ei|en)\s+(ole\s+)?(tietoa|löydy|löytynyt|pysty|voi\s+päätellä)",
    r"\bei(vät)?\s+(ole\s+)?(annet\w*|anna|tarjo\w*|saatavilla|käytettävissä)",
    r"\btietoa\b[^.\n]{0,30}\bei\b",
    r"\bei\s+käy\s+ilmi\b",
)]


# Text from the system prompt that has no business in an answer. The old
# citation example ("The F1 score is ...") was copied into answers by small
# models; the placeholders of the current format must not appear either.
PROMPT_LEAKS = ("harmonic mean of precision and recall", "<your sentence", "[S<id>")


def leaked_prompt(answer: str) -> bool:
    low = answer.lower()
    return any(p.lower() in low for p in PROMPT_LEAKS)


# A list item: a bullet, a numbered line, a line that starts in bold
# ("**Ristineva wind farm** - ...") or a Markdown table row (not the --- rule).
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+|\*\*|\|(?!\s*:?-))(.*)$", re.MULTILINE)


def listed_text(answer: str) -> str:
    """The part of an answer that actually lists items.

    When the answer is laid out as a list (bullets, numbers, bold lines or a
    table), only the list items count: a closing remark such as "Pohjankangas
    and Lumivaara are already in operation" mentions other sites without
    listing them as answers. Without list markup the whole answer counts.
    """
    items = _LIST_ITEM.findall(answer)
    return "\n".join(items) if items else answer


def is_abstention(answer: str) -> bool:
    return any(p.search(answer) for p in _ABSTAIN)


# ------------------------------------------------------------- answer prep

def strip_thinking(answer: str) -> tuple[str, int]:
    """Remove <think> blocks; return the answer and how much thinking there was."""
    thinking = sum(len(m.group(0)) for m in _THINK.finditer(answer))
    return _THINK.sub("", answer).strip(), thinking


def unsupported_numbers(answer: str, known: set[float]) -> list[str]:
    """Numbers in the answer that appear nowhere in the documents or the question.

    Citation markers and list numbering are ignored, and so are small integers
    (up to 12), which are mostly counts the model makes ("three projects").
    """
    text = _LIST_MARKER.sub(" ", _CITATION_MARKER.sub(" ", answer))
    out: list[str] = []
    for token, values in numbers_in(text):
        if all(v.is_integer() and v <= 12 for v in values):
            continue
        if not any(_close(v, k) for v in values for k in known):
            out.append(token)
    return out


def known_numbers(*texts: str) -> set[float]:
    known: set[float] = set()
    for t in texts:
        for _tok, vals in numbers_in(t):
            known |= vals
    return known


# ----------------------------------------------------------------- scoring

@dataclass
class Score:
    score: float  # 0..1: detail and unanswerable are 0/1, a list is its recall
    correct: bool
    abstained: bool
    found_items: list[str] = field(default_factory=list)
    missed_items: list[str] = field(default_factory=list)
    extra_items: list[str] = field(default_factory=list)
    precision: float | None = None
    unsupported_numbers: list[str] = field(default_factory=list)
    citations: int = 0
    citations_resolved: int = 0
    citation_hit: bool | None = None  # cites a location that holds the answer (answerable only)
    prompt_leak: bool = False  # copied text from the system prompt into the answer

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def gold_locations(question: dict, language: str, doc_ids: dict[str, str]) -> set[tuple[str, str]]:
    """(document id, locator) pairs that contain the answer."""
    evidence = list(question.get("evidence", []))
    for item in question.get("items", []):
        evidence += item.get("evidence", [])
    out = set()
    for ev in evidence:
        loc = ev["locator"]
        loc = loc[language] if isinstance(loc, dict) else loc
        out.add((doc_ids[ev["doc"]], loc))
    return out


def score_answer(
    question: dict,
    answer: str,
    *,
    documents: list[DocumentContent],
    corpus_language: str,
    doc_ids: dict[str, str],
    universes: dict[str, dict[str, list[str]]],
    known: set[float],
) -> Score:
    abstained = is_abstention(answer)
    category = question["category"]
    cites: list[Citation] = extract_citations(answer, documents)
    resolved = [c for c in cites if c.found]

    if category == "unanswerable":
        ok = abstained or matches_any(question.get("accept", []), answer)
        s = Score(score=1.0 if ok else 0.0, correct=ok, abstained=abstained)
    elif category == "list":
        found, missed = [], []
        for item in question["items"]:
            (found if matches_any(item["match"], answer) else missed).append(item["name"])
        extra: list[str] = []
        precision = None
        universe = universes.get(question.get("universe") or "")
        if universe:
            gold = {i["name"] for i in question["items"]}
            listed = listed_text(answer)
            extra = [name for name, pats in universe.items() if name not in gold and matches_any(pats, listed)]
            precision = len(found) / (len(found) + len(extra)) if (found or extra) else 0.0
        recall = len(found) / len(question["items"])
        s = Score(score=recall, correct=not missed and not extra, abstained=abstained,
                  found_items=found, missed_items=missed, extra_items=extra, precision=precision)
    else:  # detail
        ok = matches_any(question["answer"], answer)
        s = Score(score=1.0 if ok else 0.0, correct=ok, abstained=abstained)

    s.unsupported_numbers = unsupported_numbers(answer, known)
    s.prompt_leak = leaked_prompt(answer)
    s.citations = len(cites)
    s.citations_resolved = len(resolved)
    if category != "unanswerable":
        gold = gold_locations(question, corpus_language, doc_ids)
        s.citation_hit = any((c.document_id, c.resolved_locator) in gold for c in resolved)
    return s
