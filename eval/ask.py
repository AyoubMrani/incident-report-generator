#!/usr/bin/env python3
"""
eval/ask.py — ask the running assistant a question and print the full answer.

The chat endpoint streams Server-Sent Events, so a plain `curl` shows a wall of
`data:` frames rather than the answer. This consumes the stream and prints the
parsed result the way the UI renders it, which makes manual testing of any use
case a one-liner:

    python eval/ask.py "how to rollback lineIds"
    python eval/ask.py --json "kafka consumer lag"      # raw answer object
    python eval/ask.py --url http://localhost:8000 "hello"

Exit status is non-zero if the request fails, so it can be used in a script.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:8000"
CLIENT_ID = "ask-cli"


def stream_chat(base_url: str, query: str, conversation_id: str | None = None) -> dict:
    """POST to /api/chat/stream and return the final answer object.

    Returns {} if the stream ended without a `done` event (e.g. the model
    backend was unreachable), after printing whatever error was reported.
    """
    body = json.dumps({
        "query": query,
        "image_b64": None,
        "conversation_id": conversation_id,
        "links": [],
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Client-Id": CLIENT_ID},
    )

    answer: dict = {}
    tokens = 0
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                kind = event.get("type")
                if kind == "meta":
                    print(f"conversation: {event.get('conversation_id')}\n", file=sys.stderr)
                elif kind == "token":
                    tokens += 1
                    print(".", end="", flush=True, file=sys.stderr)
                elif kind == "chat":
                    answer = {"is_chat": True, "answer": event.get("text", "")}
                elif kind == "error":
                    print(f"\nERROR: {event.get('detail')}", file=sys.stderr)
                elif kind == "done":
                    answer = event.get("answer", {})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return {}
    except urllib.error.URLError as exc:
        print(f"Could not reach {base_url}: {exc.reason}", file=sys.stderr)
        return {}

    if tokens:
        print(file=sys.stderr)  # end the progress dots
    return answer


def _print_human(a: dict) -> None:
    """Render the answer the way the chat panel shows it."""
    if not a:
        print("(no answer returned)")
        return

    if a.get("is_chat"):
        tag = "CLARIFICATION" if a.get("needs_clarification") else "CHAT"
        print(f"[{tag}] {a.get('answer', '')}")
        return

    conf = a.get("confidence", 0)
    flag = " (low confidence)" if a.get("low_confidence") else ""
    print(f"{a.get('incident_type', 'Unknown')} — {conf}%{flag}")
    if a.get("refused"):
        print("[REFUSED]")
    print()

    for label, key in (
        ("PROBLEM SUMMARY", "answer"),
        ("ROOT CAUSE", "root_cause"),
        ("INVESTIGATION", "investigation"),
    ):
        if a.get(key):
            print(f"{label}\n  {a[key]}\n")

    if a.get("no_documented_resolution"):
        print("!! No documented resolution was found in the retrieved report(s).\n")

    steps = a.get("steps") or []
    if steps:
        print("RESOLUTION STEPS")
        for s in steps:
            print(f"  {s.get('step')}. [{s.get('action_type', '?')}] {s.get('title', '')}")
            if s.get("purpose"):
                print(f"      purpose: {s['purpose']}")
            if s.get("action"):
                print(f"      {s['action']}")
            art = s.get("artifact")
            if art:
                print(f"      --- {art.get('language')} ---")
                for ln in str(art.get("content", "")).splitlines():
                    print(f"      {ln}")
            if s.get("validation"):
                print(f"      validate: {s['validation']}")
            if s.get("evidence"):
                print(f"      evidence: {', '.join(s['evidence'])}")
        print()

    if a.get("has_media"):
        print("(the source report includes screenshots illustrating these steps)\n")

    if a.get("ai_suggestion"):
        print(f"AI-SUGGESTED (not documented)\n  {a['ai_suggestion']}\n")

    for label, key in (("VALIDATION", "validation"), ("NOTES", "additional_notes")):
        if a.get(key):
            print(f"{label}\n  {a[key]}\n")

    if a.get("security_note"):
        print(f"SECURITY: {a['security_note']}\n")

    sources = a.get("retrieval") or []
    print(f"SOURCES ({len(sources)})")
    for s in sources:
        ident = s.get("incident_id") or "(no id)"
        print(f"  - {ident}: {s.get('title', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the incident assistant a question.")
    parser.add_argument("query", help="the question to ask")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"base URL (default {DEFAULT_URL})")
    parser.add_argument("--json", action="store_true", help="print the raw answer object")
    parser.add_argument("--conversation", default=None, help="continue an existing conversation")
    args = parser.parse_args()

    answer = stream_chat(args.url, args.query, args.conversation)
    if args.json:
        print(json.dumps(answer, indent=2))
    else:
        _print_human(answer)
    return 0 if answer else 1


if __name__ == "__main__":
    raise SystemExit(main())
