"""
eval/benchmark_retrieval.py — measure retrieval quality on the labeled eval set.

Compares three retrieval configurations on the same queries:
  - vector : embedding (cosine) search only
  - bm25   : lexical BM25 only
  - hybrid : BM25 + vector fused with Reciprocal Rank Fusion (the shipped system)

Metrics (standard IR):
  - Recall@k  : is the gold report in the top-k results?  (k = 1, 3, 5)
  - MRR       : mean reciprocal rank of the gold report
  - nDCG@5    : rank-discounted gain (single relevant doc per query)

Results are printed as a table and returned as a dict for the notebook. The
gold label is a report (incident_id); a retrieved chunk counts as relevant if
its incident_id matches the gold.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402

from app.chatbot.ingestion import build_knowledge_base  # noqa: E402
from app.chatbot.retrieval import (  # noqa: E402
    _best_chunk_per_source,
    _fuse_query_scores,
)

EVAL = Path(__file__).resolve().parent / "eval_set.json"
KS = (1, 3, 5)
TOP = 5


def _ranked_incident_ids(hits: list[dict]) -> list[str]:
    """Ordered, de-duplicated incident_ids from a hit list."""
    out, seen = [], set()
    for h in hits:
        inc = h.get("incident_id")
        if inc and inc not in seen:
            seen.add(inc)
            out.append(inc)
    return out


def _retrieve(mode: str, query: str, kb) -> list[str]:
    """Return ranked incident_ids for one query under a retrieval mode."""
    scores = _fuse_query_scores(query, None, kb.embed_model, kb.embeddings)

    if mode == "vector":
        ranked = _best_chunk_per_source(scores, kb.documents, kb.metadata, [query], None)
    elif mode == "bm25":
        bm25_ranking = kb.bm25.rank(query)
        # Pure BM25: give the fusion a zero semantic signal so only BM25 ranks.
        ranked = _best_chunk_per_source(
            np.zeros(len(kb.documents), dtype="float32"),
            kb.documents, kb.metadata, [query], bm25_ranking,
        )
    elif mode == "hybrid":
        bm25_ranking = kb.bm25.rank(query)
        ranked = _best_chunk_per_source(scores, kb.documents, kb.metadata, [query], bm25_ranking)
    else:
        raise ValueError(mode)

    return _ranked_incident_ids(ranked)[:TOP]


def _metrics(ranked: list[str], gold: str) -> dict:
    rank = ranked.index(gold) + 1 if gold in ranked else 0
    m = {f"recall@{k}": 1.0 if (rank and rank <= k) else 0.0 for k in KS}
    m["rr"] = 1.0 / rank if rank else 0.0
    m["ndcg@5"] = (1.0 / math.log2(rank + 1)) if (rank and rank <= 5) else 0.0
    return m


def run(kb=None) -> dict:
    if kb is None:
        kb = build_knowledge_base(str(ROOT / "reports"))
    queries = json.loads(EVAL.read_text())

    results: dict[str, dict] = {}
    per_style: dict[str, dict[str, list[float]]] = {}

    for mode in ("vector", "bm25", "hybrid"):
        agg: dict[str, list[float]] = {f"recall@{k}": [] for k in KS}
        agg["rr"] = []
        agg["ndcg@5"] = []
        for q in queries:
            ranked = _retrieve(mode, q["query"], kb)
            m = _metrics(ranked, q["gold"])
            for key, val in m.items():
                agg[key].append(val)
            # per-style breakdown (recall@5 as the headline)
            per_style.setdefault(q["style"], {}).setdefault(mode, []).append(m["recall@5"])
        results[mode] = {key: float(np.mean(vals)) for key, vals in agg.items()}

    return {"overall": results, "per_style_recall@5": per_style, "n_queries": len(queries)}


def _fmt(results: dict) -> str:
    o = results["overall"]
    lines = [
        f"{'mode':<8} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'MRR':>6} {'nDCG@5':>7}",
        "-" * 44,
    ]
    for mode in ("vector", "bm25", "hybrid"):
        r = o[mode]
        lines.append(
            f"{mode:<8} {r['recall@1']:>6.3f} {r['recall@3']:>6.3f} "
            f"{r['recall@5']:>6.3f} {r['rr']:>6.3f} {r['ndcg@5']:>7.3f}"
        )
    lines.append("")
    lines.append("Recall@5 by query style:")
    ps = results["per_style_recall@5"]
    header = f"  {'style':<9}" + "".join(f"{m:>9}" for m in ("vector", "bm25", "hybrid"))
    lines.append(header)
    for style in sorted(ps):
        row = f"  {style:<9}"
        for mode in ("vector", "bm25", "hybrid"):
            vals = ps[style].get(mode, [])
            row += f"{(sum(vals) / len(vals) if vals else 0):>9.3f}"
        lines.append(row)
    return "\n".join(lines)


if __name__ == "__main__":
    res = run()
    print(f"Retrieval benchmark on {res['n_queries']} labeled queries\n")
    print(_fmt(res))
