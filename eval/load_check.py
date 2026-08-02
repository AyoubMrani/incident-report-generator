#!/usr/bin/env python3
"""
eval/load_check.py — behaviour under concurrent use.

An incident desk is not one person asking one question. Several engineers hit
the assistant during the same outage, and the parts this platform added for
speed are exactly the parts that concurrency can break:

  * the answer cache is shared mutable state (OrderedDict + lock)
  * refresh() swaps the knowledge base under live readers
  * SQLite holds conversation history for every client at once

None of that is exercised by a sequential test suite. This drives the running
server from several threads and asserts the properties that must survive:
every request answered, no cross-talk between conversations, and a cache hit
that returns the same answer as the generation it came from.

Usage:
    python eval/load_check.py                    # 6 workers, 12 requests
    python eval/load_check.py --workers 4 --requests 8
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ask import stream_chat  # noqa: E402

DEFAULT_URL = "http://localhost:8000"

QUERIES = [
    "how to rollback lineIds",
    "how to remove duplicate customers",
    "intermittent dns resolution failures for internal services",
    "kafka consumer group lag growing without bound",
    "public API certificate expired causing TLS failures",
    "java service OOM killed repeatedly under steady load",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--requests", type=int, default=12)
    args = parser.parse_args()

    plan = [QUERIES[i % len(QUERIES)] for i in range(args.requests)]
    results: list[dict] = []
    lock = threading.Lock()

    def one(index: int, query: str) -> None:
        started = time.time()
        try:
            answer = stream_chat(args.url, query)
            row = {
                "i": index, "query": query, "ok": bool(answer),
                "confidence": answer.get("confidence"),
                "n_steps": len(answer.get("steps") or []),
                "sources": [r.get("title") for r in (answer.get("retrieval") or [])],
                "seconds": round(time.time() - started, 1),
            }
        except Exception as exc:  # noqa: BLE001
            row = {"i": index, "query": query, "ok": False,
                   "error": str(exc), "seconds": round(time.time() - started, 1)}
        with lock:
            results.append(row)

    print(f"{args.requests} requests over {args.workers} concurrent workers "
          f"against {args.url}\n")
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, query in enumerate(plan):
            pool.submit(one, index, query)
    wall = time.time() - started

    results.sort(key=lambda r: r["i"])
    for row in results:
        status = "ok  " if row["ok"] else "FAIL"
        detail = row.get("error", "")
        print(f"  [{status}] {row['query'][:40]:40s} "
              f"{str(row.get('confidence','-')):>4s} {row['seconds']:6.1f}s {detail}")

    failures = [r for r in results if not r["ok"]]

    # Consistency: the same question must not come back with different answers
    # within one run. Divergence here means the cache served something that did
    # not match a fresh generation, or a KB swap landed mid-flight.
    by_query: dict[str, set] = {}
    for row in results:
        if row["ok"]:
            by_query.setdefault(row["query"], set()).add(
                json.dumps({"c": row["confidence"], "n": row["n_steps"],
                            "s": sorted(row["sources"] or [])}, sort_keys=True)
            )
    inconsistent = {q: v for q, v in by_query.items() if len(v) > 1}

    print(f"\nwall time {wall:.1f}s for {len(results)} requests")
    print(f"failures: {len(failures)}")
    print(f"inconsistent answers: {len(inconsistent)}")
    for query, variants in inconsistent.items():
        print(f"  {query[:50]}")
        for variant in variants:
            print(f"     {variant}")

    return 0 if not failures and not inconsistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
