"""
shared/fusion.py — Reciprocal Rank Fusion, shared by the two retrieval paths.

RRF combines rankings by summing 1/(k + rank) across them. Its value here is
that it needs no score calibration: cosine similarity and BM25 scores live on
unrelated scales, and normalising them against each other would be a tuning
parameter nobody could justify. Rank position is comparable by construction.

Lifted out of `chatbot/retrieval.py` so the chat-history search uses the same
fusion as the knowledge-base retrieval rather than a second implementation that
could drift. `retrieval.py` keeps its NumPy-specific wrapper and delegates the
arithmetic here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

# 60 is the constant from the original RRF paper (Cormack et al.). Larger k
# flattens the contribution of rank position; smaller k makes the top of each
# list dominate. Kept as one definition so both call sites cannot disagree.
RRF_K = 60

T = TypeVar("T")


def rrf_fuse(*rankings: Sequence[T], k: int = RRF_K) -> dict[T, float]:
    """Fuse any number of ranked id lists into id -> fused score.

    Each ranking is best-first. An id absent from a ranking simply contributes
    nothing from it, which is what lets a lexical list that matched only a few
    documents be fused with a dense list that scored all of them.
    """
    fused: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


def rrf_rank(*rankings: Sequence[T], k: int = RRF_K) -> list[tuple[T, float]]:
    """`rrf_fuse`, returned as a list ordered best-first."""
    fused = rrf_fuse(*rankings, k=k)
    return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)


def order_by_score(scores: Iterable[float]) -> list[int]:
    """Indices of `scores`, highest first — a ranking from a score vector."""
    values = list(scores)
    return sorted(range(len(values)), key=lambda i: values[i], reverse=True)
