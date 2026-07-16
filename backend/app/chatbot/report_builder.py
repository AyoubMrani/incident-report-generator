"""
chatbot/report_builder.py — turn a diagnosed conversation into an IncidentReport.

The "chat-to-report" feature: after the chatbot has diagnosed an incident, this
assembles a report in the {metadata, blocks[]} schema (app.shared.schema) so it
can be saved via the existing ReportService and opened/edited in the Report
Generator UI.

GROUNDING RULE (strict): every populated field comes from the conversation — the
user's reported symptom, the assistant's parsed resolution (incident_type,
summary, steps, artifacts), and the retrieved/cited reports. Nothing is invented.
Fields we cannot ground are left empty (schema allows empty strings) rather than
fabricated. The generator provenance (caller, date, minted id) is factual
metadata, not invented incident content.
"""

from __future__ import annotations

import re
import time
import uuid

from app.shared.schema import IncidentReport


def _uid() -> str:
    return str(uuid.uuid4())


def _first_user_symptom(messages: list[dict]) -> str:
    """The reported symptom = the first substantive user message text."""
    for m in messages:
        if m.get("role") == "user":
            text = (m.get("text") or "").strip()
            if text:
                return text
    return ""


def _latest_assistant_answer(messages: list[dict]) -> dict | None:
    """The most recent assistant answer payload (the diagnosis to report on)."""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            payload = m.get("payload")
            if isinstance(payload, dict) and "incident_type" in payload:
                return payload
    return None


def _plain_paragraph(text: str) -> str:
    """Wrap grounded text as a paragraph block content (HTML, like real reports)."""
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<p>{safe}</p>"


class NoDiagnosisError(Exception):
    """Raised when the conversation has no diagnosed incident to report on."""


def build_report_from_conversation(
    messages: list[dict],
    *,
    now: float | None = None,
) -> tuple[IncidentReport, str]:
    """Build an IncidentReport (+ markdown mirror) strictly from `messages`.

    `messages` is the stored conversation (list of {role, text, payload, ...}).
    Returns (report, markdown). Raises NoDiagnosisError if the conversation was
    never diagnosed (greeting-only, clarification-only, or no assistant answer).
    """
    answer = _latest_assistant_answer(messages)
    if answer is None or answer.get("is_chat") or answer.get("needs_clarification"):
        raise NoDiagnosisError(
            "This conversation has no diagnosed incident to turn into a report."
        )

    symptom = _first_user_symptom(messages)
    incident_type = str(answer.get("incident_type") or "").strip() or "Incident"
    summary = str(answer.get("incident_summary") or answer.get("answer") or "").strip()
    steps = [
        str(s.get("action") or s.get("title") or "").strip()
        for s in (answer.get("recommended_resolution") or answer.get("steps") or [])
        if isinstance(s, dict) and (s.get("action") or s.get("title"))
    ]
    artifacts = [
        a for a in (answer.get("artifacts") or [])
        if isinstance(a, dict) and str(a.get("content") or "").strip()
    ]
    matched_ids = [
        str(mid).strip()
        for mid in (answer.get("matched_report_ids") or [])
        if str(mid).strip()
    ]

    # ── metadata (grounded; provenance fields are factual, not invented) ───────
    ts = int((now if now is not None else time.time()))
    minted_id = f"CHAT-{ts}"
    # Title = the diagnosed incident type (grounded), trimmed to a filename-safe
    # length. category mirrors the incident type. We do NOT fabricate caller data.
    title = incident_type[:120]

    metadata: dict = {
        "incident_id": minted_id,
        "title": title,
        "caller": "Chatbot (auto-generated)",
        "category": incident_type,
        "subcategory": "",  # not grounded -> empty, never invented
        "date": time.strftime("%Y-%m-%d", time.localtime(ts)),
    }
    # Optional grounded extras (schema allows extra fields). Only add when the
    # conversation actually supports them.
    confidence = answer.get("confidence")
    if isinstance(confidence, int):
        metadata["confidence"] = str(confidence)
    # affected_service: derive ONLY from cited report titles, else omit.
    src_titles = [
        (s.get("title") or "").strip()
        for s in (answer.get("retrieval") or [])
        if isinstance(s, dict) and (s.get("title") or "").strip()
    ]
    if src_titles:
        metadata["affected_service"] = src_titles[0][:120]

    # ── blocks (grounded) ──────────────────────────────────────────────────────
    blocks: list[dict] = [
        {"id": _uid(), "type": "heading", "level": 1, "content": title, "title": title},
    ]
    if symptom:
        blocks.append({
            "id": _uid(), "type": "paragraph", "title": "Reported Symptom",
            "content": _plain_paragraph(symptom),
        })
    if summary:
        blocks.append({
            "id": _uid(), "type": "paragraph", "title": "Root Cause",
            "content": _plain_paragraph(summary),
        })
    if steps:
        blocks.append({
            "id": _uid(), "type": "list", "title": "Resolution Steps",
            "ordered": True, "label": "", "items": steps,
        })
    for a in artifacts:
        blocks.append({
            "id": _uid(), "type": "code",
            "items": [{
                "id": _uid(), "type": "code",
                "title": str(a.get("title") or "Supporting artifact"),
                "header": "",
                "content": str(a["content"]),
                "language": str(a.get("language") or "text"),
            }],
        })
    for mid in matched_ids:
        blocks.append({
            "id": _uid(), "type": "incident_example", "title": "Related incident",
            "incident_id": mid, "link": "",
        })

    report = IncidentReport(metadata=metadata, blocks=blocks)  # validates on build
    markdown = _to_markdown(title, symptom, summary, steps, artifacts, matched_ids)
    return report, markdown


def _to_markdown(title, symptom, summary, steps, artifacts, matched_ids) -> str:
    lines = [f"# {title}", ""]
    if symptom:
        lines += ["## Reported Symptom", symptom, ""]
    if summary:
        lines += ["## Root Cause", summary, ""]
    if steps:
        lines += ["## Resolution Steps"]
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        lines.append("")
    for a in artifacts:
        lang = a.get("language") or "text"
        lines += [f"### {a.get('title') or 'Artifact'}", f"```{lang}", str(a["content"]), "```", ""]
    if matched_ids:
        lines += ["## Related incidents"] + [f"- {mid}" for mid in matched_ids]
    return "\n".join(lines)
