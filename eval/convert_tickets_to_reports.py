"""
eval/convert_tickets_to_reports.py — turn the 40 flat tickets into real reports.

The chatbot ingests reports in the Report-Generator format:
    {editingFilename, markdown, report: {metadata, blocks[]}}
so the synthetic tickets must be written in exactly that shape (one file per
ticket in reports/) to be retrievable — identical to what the generator page
produces. This maps each flat ticket field onto the right block type.

Field mapping:
    reported_symptom  -> paragraph  (title "Reported Symptom")
    root_cause        -> paragraph  (title "Root Cause", HTML-wrapped like real reports)
    error_details     -> code block (title "Error Details", the log/error snippet)
    resolution_steps  -> ordered list (title "Resolution Steps")
    domain/severity/… -> metadata (category=domain, subcategory=affected_service, priority=severity)
    tags              -> a trailing paragraph so tags are searchable text
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TICKETS = Path(__file__).resolve().parent / "synthetic_tickets.json"
REPORTS = ROOT / "reports"


def _uid() -> str:
    return str(uuid.uuid4())


def _domain_language(error_details: str, domain: str) -> str:
    """Pick a plausible code-fence language for the error snippet."""
    if re.search(r"\bSQLSTATE\b|\bERROR:\b|pg_stat|deadlock", error_details):
        return "sql"
    if re.search(r"HTTP/|WWW-Authenticate|status", error_details):
        return "http"
    return "text"


def _safe_filename(incident_id: str, title: str) -> str:
    safe_title = re.sub(r"[^A-Za-z0-9]+", " ", title).strip().replace(" ", " ")
    return f"{incident_id}_{safe_title}.json"


def build_report(t: dict) -> dict:
    inc = t["ticket_id"]
    title = t["title"]

    blocks = [
        {"id": _uid(), "type": "heading", "level": 1, "content": title, "title": title},
        {
            "id": _uid(), "type": "paragraph", "title": "Reported Symptom",
            "content": f"<p>{t['reported_symptom']}</p>",
        },
        {
            "id": _uid(), "type": "paragraph", "title": "Root Cause",
            "content": f"<p>{t['root_cause']}</p>",
        },
        {
            "id": _uid(), "type": "code",
            "items": [{
                "id": _uid(), "type": "code",
                "title": "Error Details",
                "header": f"{t['affected_service']} — error / log snippet",
                "content": t["error_details"],
                "language": _domain_language(t["error_details"], t["domain"]),
            }],
        },
        {
            "id": _uid(), "type": "list", "title": "Resolution Steps",
            "ordered": True, "label": "",
            "items": list(t["resolution_steps"]),
        },
        {
            "id": _uid(), "type": "paragraph", "title": "Tags",
            "content": f"<p>{', '.join(t['tags'])}</p>",
        },
    ]

    metadata = {
        "incident_id": inc,
        "title": title,
        "caller": "System Generated",
        "category": t["domain"],
        "subcategory": t["affected_service"],
        "date": "2026-07-05",
        "priority": t["severity"],
    }

    # markdown mirror (what the generator stores for preview/search)
    md = [f"# {title}", "", t["reported_symptom"], "", t["root_cause"], ""]
    for i, step in enumerate(t["resolution_steps"], 1):
        md.append(f"{i}. {step}")
    md += ["", "Error Details", "```", t["error_details"], "```",
           "", f"Tags: {', '.join(t['tags'])}"]

    return {
        "editingFilename": None,
        "markdown": "\n".join(md),
        "report": {"metadata": metadata, "blocks": blocks},
    }


def main(write: bool = True) -> list[str]:
    tickets = json.loads(TICKETS.read_text())
    written = []
    for t in tickets:
        report = build_report(t)
        fname = _safe_filename(t["ticket_id"], t["title"])
        if write:
            (REPORTS / fname).write_text(json.dumps(report, indent=2), encoding="utf-8")
        written.append(fname)
    return written


if __name__ == "__main__":
    files = main(write=True)
    print(f"wrote {len(files)} reports into {REPORTS}")
    for f in files[:5]:
        print("  ", f)
    print("   ...")
