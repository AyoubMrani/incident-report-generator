"""
chatbot/answer_html.py — render a chat answer as a self-contained HTML fragment.

The chat panel renders the structured answer as React components, which is right
for interaction (feedback, citations, syntax highlighting). But a documented
procedure often depends on screenshots, and those live inside the source report
rather than in the answer object. This module produces the report-style HTML view
of an answer, with the source report's images embedded in place, for reading and
for export.

The fragment carries no <html>/<head>/<body> wrapper so it can be dropped into a
panel, and no external references so it survives being saved to a file.
"""

from __future__ import annotations

import html
import re

# Section order matches the incident-response layout used throughout the app.
_LANG_LABEL = {
    "SQL_QUERY": "Data extraction (SQL)",
    "CODE": "Script / Terminal",
    "CONFIG_CHANGE": "Configuration change",
    "INFRA_ACTION": "Infrastructure action",
    "INVESTIGATION_MEDIA": "Screenshots / media",
    "LOG_ANALYSIS": "Log analysis",
    "MANUAL_PROCEDURE": "Manual procedure",
    "DOC_REFERENCE": "Documentation reference",
}

_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


def extract_images(report: dict) -> list[str]:
    """Every <img> tag in a report, in document order.

    Screenshots are authored inline in paragraph HTML (often as base64 data
    URIs) as well as in dedicated image blocks, so both are collected.
    """
    images: list[str] = []
    blocks = report.get("blocks") or []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image" and block.get("data_url"):
            caption = html.escape(str(block.get("caption") or ""))
            images.append(
                f'<figure><img src="{html.escape(str(block["data_url"]), quote=True)}" '
                f'alt="{caption}" /><figcaption>{caption}</figcaption></figure>'
            )
            continue
        content = block.get("content")
        if isinstance(content, str):
            images.extend(_IMG_TAG.findall(content))
    return images


def _esc(text) -> str:
    return html.escape(str(text or ""))


def _section(title: str, body: str) -> str:
    return f"<h3>{title}</h3>\n{body}\n" if body.strip() else ""


def _render_step(step: dict, images: list[str]) -> str:
    """One resolution step, formatted by its solution type."""
    action_type = str(step.get("action_type") or "MANUAL_PROCEDURE")
    label = _LANG_LABEL.get(action_type, "Step")
    out = [f"<p><strong>Step {_esc(step.get('step'))} — {_esc(step.get('title'))}"
           f" ({_esc(label)})</strong></p>"]

    if step.get("purpose"):
        out.append(f"<p><em>Purpose:</em> {_esc(step['purpose'])}</p>")
    if step.get("action"):
        out.append(f"<p>{_esc(step['action'])}</p>")

    artifact = step.get("artifact")
    if artifact and artifact.get("content"):
        lang = _esc(artifact.get("language") or "text")
        code = _esc(artifact["content"])
        if action_type == "LOG_ANALYSIS":
            out.append(f"<blockquote><pre>{code}</pre></blockquote>")
        else:
            out.append(f'<pre><code class="language-{lang}">{code}</code></pre>')

    # A step may reference a screenshot by position, e.g. "[SCREENSHOT 3]".
    for marker in re.findall(r"\[SCREENSHOT (\d+)\]", str(step.get("action") or "")):
        index = int(marker) - 1
        if 0 <= index < len(images):
            out.append(images[index])

    if step.get("validation"):
        out.append(f"<p><em>Validate:</em> {_esc(step['validation'])}</p>")
    if step.get("evidence"):
        out.append(f"<p><em>Evidence:</em> {_esc(', '.join(step['evidence']))}</p>")
    return "\n".join(out)


def render_answer_html(answer: dict, report: dict | None = None) -> str:
    """Render an answer as an HTML fragment, embedding `report`'s screenshots."""
    images = extract_images(report) if report else []

    if answer.get("is_chat"):
        return f'<div class="incident-response"><p>{_esc(answer.get("answer"))}</p></div>'

    parts: list[str] = ['<div class="incident-response">']

    confidence = answer.get("confidence", 0)
    parts.append(
        f'<p class="meta"><strong>{_esc(answer.get("incident_type") or "Incident")}</strong>'
        f" — {_esc(confidence)}% confidence</p>"
    )
    if answer.get("security_note"):
        parts.append(f'<p class="warning">{_esc(answer["security_note"])}</p>')

    parts.append(_section("📋 Problem Summary", f"<p>{_esc(answer.get('answer'))}</p>"
                          if answer.get("answer") else ""))
    parts.append(_section("🔍 Root Cause", f"<p>{_esc(answer.get('root_cause'))}</p>"
                          if answer.get("root_cause") else ""))
    parts.append(_section("🕵️ Investigation", f"<p>{_esc(answer.get('investigation'))}</p>"
                          if answer.get("investigation") else ""))

    if answer.get("no_documented_resolution"):
        parts.append('<p class="warning">No documented resolution was found in the '
                     "retrieved incident report(s) for this issue.</p>")

    steps = answer.get("steps") or answer.get("recommended_resolution") or []
    if steps:
        body = "\n".join(_render_step(s, images) for s in steps)
        # Screenshots the steps did not reference explicitly still belong to the
        # procedure, so show them once at the end rather than dropping them.
        referenced = {
            int(m) - 1
            for s in steps
            for m in re.findall(r"\[SCREENSHOT (\d+)\]", str(s.get("action") or ""))
        }
        leftover = [img for i, img in enumerate(images) if i not in referenced]
        if leftover:
            body += ('\n<p><em>📸 Screenshots from the source report illustrating '
                     "these steps:</em></p>\n" + "\n".join(leftover))
        parts.append(_section("🛠️ Resolution Steps", body))
    elif images:
        parts.append(_section("📸 Screenshots from the source report",
                              "\n".join(images)))

    if answer.get("ai_suggestion"):
        parts.append(
            '<h3>🤖 AI-Suggested Recommendation (not a documented resolution)</h3>'
            f'<p class="ai-suggestion">{_esc(answer["ai_suggestion"])}</p>'
        )

    parts.append(_section("✅ Validation / Verification",
                          f"<p>{_esc(answer.get('validation'))}</p>"
                          if answer.get("validation") else ""))
    parts.append(_section("📝 Additional Notes",
                          f"<p>{_esc(answer.get('additional_notes'))}</p>"
                          if answer.get("additional_notes") else ""))

    sources = answer.get("retrieval") or []
    if sources:
        items = "".join(
            f"<li>{_esc(s.get('incident_id') or '')} {_esc(s.get('title') or '')}</li>"
            for s in sources
        )
        parts.append(_section("Sources", f"<ul>{items}</ul>"))

    parts.append("</div>")
    return "\n".join(p for p in parts if p)
