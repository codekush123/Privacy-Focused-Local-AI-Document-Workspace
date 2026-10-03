"""Okapi BM25 ranking in plain Python.

Deliberately lexical and dependency-free: no vector database, no embedding
model to download, no extra service, nothing that could send text anywhere.
For document question answering the query usually shares vocabulary with the
passage that answers it, which is exactly the case BM25 is good at, and the
ranking is deterministic - the same question always retrieves the same
passages, which matters for an evaluation that compares strategies.

Unicode-aware tokenisation keeps Finnish, Chinese, Arabic and Russian working:
CJK characters are indexed individually because they are not space separated.

Stemming (Snowball, pure Python) is applied per document language. Finnish
needs it badly: one noun has a dozen case endings ("tuulipuisto",
"tuulipuiston", "tuulipuistossa"), and without stemming a question that uses a
different case than the passage simply does not match. The benchmark measures
the difference (``LDW_RETRIEVAL_STEMMING=false`` switches it off).
"""
from __future__ import annotations

import math
import re
from collections import Counter

import snowballstemmer

from app.config import settings

from .chunker import Chunk

K1 = 1.5
B = 0.75

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CJK = re.compile(r"[　-鿿豈-﫿･-ￜ]")

# Words too common to help ranking. Kept short and English-only on purpose: an
# aggressive multilingual stop list would hurt the other languages.
EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "was", "were", "be", "been",
    "for", "on", "with", "as", "by", "at", "from", "that", "this", "these", "those", "it", "its",
    "what", "which", "who", "how", "why", "when", "where", "do", "does", "did", "can", "could",
    "would", "should", "please", "give", "tell", "me", "my", "you", "your", "i", "we", "they",
}
# Question words and particles that appear in almost every Finnish question.
FI_STOPWORDS = {
    "ja", "tai", "on", "ovat", "oli", "olivat", "ei", "se", "ne", "että", "kun", "jos", "mikä",
    "mitkä", "mitä", "missä", "mistä", "mihin", "milloin", "kuka", "ketkä", "kenen", "kuinka",
    "paljonko", "montako", "miten", "miksi", "minkä", "mikäli", "kaikki", "kaikkien", "myös",
    "sekä", "kerro", "luettele", "anna", "minulle", "onko", "oliko", "voi", "tämä", "nämä",
}
STOPWORDS = EN_STOPWORDS | FI_STOPWORDS

_STEMMERS = {"en": snowballstemmer.stemmer("english"), "fi": snowballstemmer.stemmer("finnish")}

# Very common function words, used only to guess a document's language.
_LANG_MARKERS = {
    "en": {"the", "and", "of", "to", "is", "was", "in", "for", "with", "that", "are", "by"},
    "fi": {"ja", "on", "oli", "ovat", "ei", "että", "sekä", "mukaan", "vuonna", "joka", "jonka", "myös", "kanssa", "tai"},
}


def detect_language(text: str) -> str | None:
    """'en', 'fi' or None. Deliberately simple: counts frequent function words."""
    words = _WORD.findall(text.lower()[:20000])
    if not words:
        return None
    counts = {lang: sum(1 for w in words if w in markers) for lang, markers in _LANG_MARKERS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] >= 3 else None


# Finnish compounds and consonant gradation defeat the stemmer
# ("käyttöönottopäivä" vs "käyttöönotto", "Pohjankangas" vs "Pohjankankaan").
# Long Finnish words therefore also index their first characters.
PREFIX_MIN_WORD = 8


def tokenize(text: str, language: str | None = None) -> list[str]:
    stem = _STEMMERS.get(language or "") if settings.retrieval_stemming else None
    prefix = settings.retrieval_prefix_chars if (language == "fi" and settings.retrieval_stemming) else 0
    tokens: list[str] = []
    for word in _WORD.findall(text.lower()):
        if _CJK.search(word):
            tokens.extend(ch for ch in word if not ch.isspace())
        elif len(word) > 1 and word not in STOPWORDS:
            tokens.append(stem.stemWord(word) if stem else word)
            if prefix and len(word) >= PREFIX_MIN_WORD:
                tokens.append("~" + word[:prefix])
    return tokens


def content_terms(query: str) -> list[str]:
    """Query terms that can actually match something; empty means 'not searchable'.

    The question is stemmed both ways (English and Finnish) because a document's
    language and the question's language need not match, and a stem that does
    not exist in the index simply scores nothing.
    """
    terms = tokenize(query)
    if not settings.retrieval_stemming:
        return terms
    seen: dict[str, None] = {}
    for lang in _STEMMERS:
        for t in tokenize(query, lang):
            seen.setdefault(t, None)
    return list(seen)


class Bm25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        # Guess the language once per document, from all of its passages.
        texts: dict[str, list[str]] = {}
        for c in chunks:
            texts.setdefault(c.document_id, []).append(c.text)
        self.languages = {doc_id: detect_language(" ".join(parts)) for doc_id, parts in texts.items()}
        for c in chunks:
            if not c.tokens:
                # The section title (a slide title, a Word heading) is searchable too.
                indexed = f"{c.title}\n{c.text}" if c.title and settings.retrieval_index_titles else c.text
                c.tokens = tokenize(indexed, self.languages.get(c.document_id))
        self.lengths = [len(c.tokens) or 1 for c in chunks]
        self.avg_length = sum(self.lengths) / len(self.lengths) if chunks else 1.0
        self.freqs: list[Counter[str]] = [Counter(c.tokens) for c in chunks]
        df: Counter[str] = Counter()
        for f in self.freqs:
            df.update(f.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query_terms: list[str]) -> list[float]:
        scores = [0.0] * len(self.chunks)
        for term in query_terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freq in enumerate(self.freqs):
                tf = freq.get(term, 0)
                if not tf:
                    continue
                norm = tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lengths[i] / self.avg_length))
                scores[i] += idf * norm
        return scores

    def search(self, query: str, top_k: int) -> list[tuple[Chunk, float]]:
        terms = content_terms(query)
        if not terms:
            return []
        scored = [(c, s) for c, s in zip(self.chunks, self.score(terms)) if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
