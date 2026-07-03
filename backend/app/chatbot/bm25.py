"""
chatbot/bm25.py — a small, dependency-free BM25 lexical index.

Semantic (embedding) search is weak on exact tokens — INC numbers, table names,
status codes, function names (fm_opv, support_remove_opv_duplicate, D-status).
BM25 is strong exactly there. We fuse the two (see retrieval.py, RRF) so the
final ranking gets both meaning and exact-term matching.

This is Okapi BM25 in ~50 lines rather than a new dependency: it's a stable,
well-understood formula, and keeping it in-repo means reproducible behaviour and
no supply-chain surface (the app must run fully local/offline).
"""

from __future__ import annotations

import math
import re
from collections import Counter

# BM25 free parameters (standard defaults; not data-specific / not hardcoded to
# these reports — they generalize).
_K1 = 1.5   # term-frequency saturation
_B = 0.75   # length normalization

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word/id tokens. Keeps underscores so function/table names like
    `support_remove_opv_duplicate` stay whole; keeps short tokens like INC ids."""
    return _TOKEN_RE.findall((text or "").lower())


class BM25Index:
    """Okapi BM25 over a fixed corpus of documents (one entry per chunk)."""

    def __init__(self, documents: list[str]):
        self.doc_tokens: list[list[str]] = [tokenize(d) for d in documents]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.n = len(documents)
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0

        # Document frequency per term, then idf.
        df: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            for term in set(tokens):
                df[term] += 1
        # BM25+ style idf, floored at 0 so common terms can't push scores negative.
        self.idf: dict[str, float] = {
            term: max(0.0, math.log((self.n - freq + 0.5) / (freq + 0.5) + 1.0))
            for term, freq in df.items()
        }
        # Precompute term frequencies per doc for fast scoring.
        self.doc_tf: list[Counter[str]] = [Counter(t) for t in self.doc_tokens]

    def scores(self, query: str) -> list[float]:
        """BM25 score of the query against every document (index-aligned)."""
        q_terms = [t for t in tokenize(query) if t in self.idf]
        out = [0.0] * self.n
        if not q_terms or self.avgdl == 0:
            return out
        for i in range(self.n):
            tf = self.doc_tf[i]
            dl = self.doc_len[i]
            denom_norm = _K1 * (1 - _B + _B * dl / self.avgdl)
            s = 0.0
            for term in q_terms:
                f = tf.get(term, 0)
                if f:
                    s += self.idf[term] * (f * (_K1 + 1)) / (f + denom_norm)
            out[i] = s
        return out

    def rank(self, query: str, top_k: int | None = None) -> list[int]:
        """Return document indices sorted by BM25 score (desc). Zero-score docs
        are dropped so they don't pollute the fusion with noise."""
        scored = [(i, s) for i, s in enumerate(self.scores(query)) if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        idxs = [i for i, _ in scored]
        return idxs[:top_k] if top_k else idxs
