"""Okapi BM25 ranking in plain Python.

Deliberately lexical and dependency-free: no vector database, no embedding
model to download, no extra service, nothing that could send text anywhere.
For document question answering the query usually shares vocabulary with the
passage that answers it, which is exactly the case BM25 is good at, and the
ranking is deterministic - the same question always retrieves the same
passages, which matters for an evaluation that compares strategies.

Unicode-aware tokenisation keeps Finnish, Chinese, Arabic and Russian working:
CJK characters are indexed individually because they are not space separated.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .chunker import Chunk

K1 = 1.5
B = 0.75

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CJK = re.compile(r"[　-鿿豈-﫿･-ￜ]")

# Words too common to help ranking. Kept short and English-only on purpose: an
# aggressive multilingual stop list would hurt the other languages.
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "was", "were", "be", "been",
    "for", "on", "with", "as", "by", "at", "from", "that", "this", "these", "those", "it", "its",
    "what", "which", "who", "how", "why", "when", "where", "do", "does", "did", "can", "could",
    "would", "should", "please", "give", "tell", "me", "my", "you", "your", "i", "we", "they",
}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD.findall(text.lower()):
        if _CJK.search(word):
            tokens.extend(ch for ch in word if not ch.isspace())
        elif len(word) > 1 and word not in STOPWORDS:
            tokens.append(word)
    return tokens


def content_terms(query: str) -> list[str]:
    """Query terms that can actually match something; empty means 'not searchable'."""
    return tokenize(query)


class Bm25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        for c in chunks:
            if not c.tokens:
                c.tokens = tokenize(c.text)
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
