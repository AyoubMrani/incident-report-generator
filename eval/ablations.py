"""
eval/ablations.py — sensitivity of retrieval to key hyperparameters.

Runs the retrieval benchmark (hybrid) while varying one knob at a time, so the
report can justify the chosen defaults with numbers instead of assertion:

  - chunk_size : how documents are split before embedding (700 default)
  - top_k      : how many hits retrieval returns (5 default)

Each run rebuilds the KB (chunk_size changes the index) or re-scores (top_k),
then reports Recall@5 / MRR / nDCG@5 on the labeled eval set.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.chatbot.config as cfg  # noqa: E402
import app.chatbot.ingestion as ingestion  # noqa: E402
from app.chatbot.ingestion import build_knowledge_base  # noqa: E402

import benchmark_retrieval as bench  # noqa: E402 (same dir)


def _hybrid_scores(kb) -> dict:
    """Overall hybrid metrics for a KB, via the benchmark's own machinery."""
    res = bench.run(kb=kb)
    return res["overall"]["hybrid"]


def ablate_chunk_size(sizes=(400, 700, 1000)) -> list[dict]:
    rows = []
    original = cfg.CHUNK_SIZE
    for size in sizes:
        # _chunk() reads CHUNK_SIZE at call time via its default arg -> patch it.
        cfg.CHUNK_SIZE = size
        importlib.reload(ingestion)  # pick up the new default in _chunk
        kb = ingestion.build_knowledge_base(str(ROOT / "reports"))
        m = _hybrid_scores(kb)
        rows.append({"chunk_size": size, "recall@5": m["recall@5"],
                     "mrr": m["rr"], "ndcg@5": m["ndcg@5"], "n_chunks": len(kb.documents)})
    cfg.CHUNK_SIZE = original
    importlib.reload(ingestion)
    return rows


def ablate_top_k(kb, ks=(1, 3, 5, 10)) -> list[dict]:
    """top_k only changes how many results we keep, so reuse one KB and vary the
    cutoff by re-reading the eval set through the benchmark at different TOP."""
    rows = []
    original = bench.TOP
    for k in ks:
        bench.TOP = k
        # Recompute KS-limited metrics: recall@min(k,5) is the meaningful headline.
        res = bench.run(kb=kb)
        m = res["overall"]["hybrid"]
        rows.append({"top_k": k, "recall@5": m["recall@5"], "mrr": m["rr"]})
    bench.TOP = original
    return rows


if __name__ == "__main__":
    print("=== chunk_size ablation (hybrid) ===")
    cs = ablate_chunk_size()
    print(json.dumps(cs, indent=2))

    print("\n=== top_k ablation (hybrid) ===")
    kb = build_knowledge_base(str(ROOT / "reports"))
    tk = ablate_top_k(kb)
    print(json.dumps(tk, indent=2))
