"""Translate a chat answer while keeping its citations working.

The model only translates prose. Citation markers such as ``[S1: Page 3]`` are
swapped for neutral placeholders before the model sees the text and put back
afterwards, so a translation can never break, translate or invent a citation:
the app checks every placeholder came back and re-attaches any the model lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.features.citations import CITATION_RE, normalize_citations
from app.services.llm.client import llm_client

PLACEHOLDER = "[[C{n}]]"
_PLACEHOLDER_RE = re.compile(r"\[\[\s*C\s*(\d+)\s*\]\]", re.IGNORECASE)

LANGUAGE_NAMES = {"en": "English", "fi": "Finnish"}

SYSTEM = (
    "You are a professional translator. Translate the user's text into {language}. "
    "Keep the Markdown structure exactly: headings, bullet points, numbered lists, tables, bold and italics. "
    "Keep names, numbers, units, codes and dates' values unchanged; write numbers and dates the way {language} "
    "normally writes them. Placeholders like [[C1]] mark citations: copy every placeholder unchanged to the same "
    "place in the sentence. Output only the translation, with no introduction or notes."
)


@dataclass
class Translation:
    text: str
    language: str
    markers_total: int
    markers_restored: int  # put back where the model left them
    markers_reattached: int  # the model dropped them; appended to the end of the text


def language_name(code_or_name: str) -> str:
    value = (code_or_name or "").strip()
    return LANGUAGE_NAMES.get(value.lower(), value[:40] or "English")


def protect(text: str) -> tuple[str, list[str]]:
    markers: list[str] = []

    def sub(m: re.Match) -> str:
        markers.append(m.group(0))
        return PLACEHOLDER.format(n=len(markers))

    return CITATION_RE.sub(sub, normalize_citations(text)), markers


def restore(text: str, markers: list[str]) -> tuple[str, int, int]:
    seen: set[int] = set()

    def sub(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= len(markers):
            seen.add(n)
            return markers[n - 1]
        return ""

    out = _PLACEHOLDER_RE.sub(sub, text)
    missing = [markers[i - 1] for i in range(1, len(markers) + 1) if i not in seen]
    if missing:
        out = out.rstrip() + "\n\n" + " ".join(dict.fromkeys(missing))
    return out, len(seen), len(missing)


async def translate_answer(text: str, language: str, max_tokens: int | None = None) -> Translation:
    lang = language_name(language)
    protected, markers = protect(text)
    messages = [
        {"role": "system", "content": SYSTEM.format(language=lang)},
        {"role": "user", "content": protected},
    ]
    # Translations are roughly as long as the source; Finnish needs more tokens per word.
    budget = max_tokens or min(4096, max(256, int(len(protected) / 2)))
    raw = await llm_client.chat(messages, max_tokens=budget, temperature=0.1)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    restored, kept, reattached = restore(raw, markers)
    return Translation(restored, lang, len(markers), kept, reattached)
