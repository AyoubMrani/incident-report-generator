"""
eval/corpus_eda.py — exploratory data analysis of the incident report corpus.

Produces descriptive statistics and figures for the report's "data" chapter:
  - report count, category distribution
  - document length distribution (tokens per report)
  - block-type composition (what report content looks like)
  - chunk count after splitting

Figures are written to eval/figures/*.png for inclusion in the thesis.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

from app.chatbot.ingestion import _read_json, _chunk  # noqa: E402

REPORTS = ROOT / "reports"
FIG = Path(__file__).resolve().parent / "figures"
FIG.mkdir(exist_ok=True)


def _unwrap(data: dict) -> dict:
    return data.get("report", data) if isinstance(data.get("report"), dict) else data


def collect() -> dict:
    categories: Counter[str] = Counter()
    block_types: Counter[str] = Counter()
    token_counts: list[int] = []
    chunk_counts: list[int] = []
    n_reports = 0

    for path in sorted(REPORTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        report = _unwrap(data)
        meta = report.get("metadata", {})
        if not meta.get("title"):
            continue
        n_reports += 1
        categories[meta.get("category", "Unknown")] += 1
        for b in report.get("blocks", []):
            block_types[b.get("type", "?")] += 1
        clean = _read_json(str(path))
        token_counts.append(len(re.findall(r"\w+", clean)))
        chunk_counts.append(len(_chunk(clean)))

    return {
        "n_reports": n_reports,
        "categories": dict(categories),
        "block_types": dict(block_types),
        "token_counts": token_counts,
        "chunk_counts": chunk_counts,
    }


def make_figures(stats: dict) -> list[str]:
    paths = []

    # 1. Category distribution
    cats = sorted(stats["categories"].items(), key=lambda x: x[1], reverse=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh([c for c, _ in cats][::-1], [n for _, n in cats][::-1], color="#4C78A8")
    ax.set_title("Incident reports by category")
    ax.set_xlabel("count")
    fig.tight_layout()
    p = FIG / "categories.png"; fig.savefig(p, dpi=120); plt.close(fig); paths.append(str(p))

    # 2. Token-length distribution
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(stats["token_counts"], bins=12, color="#72B7B2", edgecolor="white")
    ax.set_title("Report length distribution")
    ax.set_xlabel("tokens per report"); ax.set_ylabel("reports")
    fig.tight_layout()
    p = FIG / "lengths.png"; fig.savefig(p, dpi=120); plt.close(fig); paths.append(str(p))

    # 3. Block-type composition
    bt = sorted(stats["block_types"].items(), key=lambda x: x[1], reverse=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([b for b, _ in bt], [n for _, n in bt], color="#E45756")
    ax.set_title("Content block types across the corpus")
    ax.set_ylabel("count"); plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    p = FIG / "block_types.png"; fig.savefig(p, dpi=120); plt.close(fig); paths.append(str(p))

    return paths


if __name__ == "__main__":
    s = collect()
    import statistics as st
    print(f"reports: {s['n_reports']}")
    print(f"categories: {len(s['categories'])} distinct")
    print(f"tokens/report: median={st.median(s['token_counts'])}, "
          f"min={min(s['token_counts'])}, max={max(s['token_counts'])}")
    print(f"chunks total: {sum(s['chunk_counts'])}")
    print(f"block types: {s['block_types']}")
    figs = make_figures(s)
    print("figures written:")
    for f in figs:
        print("  ", f)
