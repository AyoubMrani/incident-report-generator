"""
resolution.py — parse and render expert JSON resolutions from the LLM.
"""

import json
import re

import streamlit as st


_SECTION_HEADERS = ("INCIDENT TYPE", "STEPS", "WARNINGS", "MISSING")
_EMPTY_MARKERS = frozenset({"none", "-", "n/a", ""})


def _empty_result(raw: str) -> dict:
    return {
        "incident_summary": "",
        "problem_summary": "",
        "incident_type": "Unknown",
        "confidence": 0,
        "similar_incidents": [],
        "matched_reports": [],
        "recommended_resolution": [],
        "supporting_sql": [],
        "possible_sql": [],
        "possible_tables": [],
        "reasoning": "",
        "alternative_resolution": [],
        "missing_information": [],
        "notes": [],
        "steps": [],
        "warnings": [],
        "missing": [],
        "insufficient": False,
        "raw": raw,
    }


def format_retrieval_context(results: list[dict], limit: int = 5) -> str:
    """Format retrieval hits with scores for the resolution prompt."""
    blocks: list[str] = []
    for chunk in results[:limit]:
        score_pct = int(float(chunk.get("score", 0)) * 100)
        blocks.append(
            "\n".join([
                f"RETRIEVAL_SIMILARITY: {score_pct}%",
                f"INCIDENT_ID: {chunk.get('incident_id') or 'unknown'}",
                f"TITLE: {chunk.get('title', '')}",
                f"SOURCE: {chunk.get('source', '')}",
                f"CONTENT:\n{chunk.get('text', '')}",
            ])
        )
    return "\n\n---\n\n".join(blocks)


def _extract_json_blob(raw: str) -> dict | None:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_confidence(value) -> int:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    if 0 < num <= 1.0:
        num *= 100
    return max(0, min(100, int(round(num))))


def _coerce_similarity(value) -> int:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    if 0 < num <= 1.0:
        num *= 100
    return max(0, min(100, int(round(num))))


def _sql_text(entry) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(entry.get("sql") or entry.get("query") or "").strip()
    return str(entry).strip()


def _parse_resolution_step(item: dict, default_step: int) -> dict | None:
    action = str(item.get("action") or "").strip()
    title = str(item.get("title") or action or "").strip()
    if not action and not title:
        return None

    evidence = item.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    evidence = [str(e).strip() for e in evidence if str(e).strip()]

    return {
        "step": _coerce_int(item.get("step"), default_step),
        "title": title,
        "purpose": str(item.get("purpose") or "").strip(),
        "action": action or title,
        "validation": str(item.get("validation") or "").strip(),
        "evidence": evidence,
    }


def _normalize_from_json(data: dict, raw: str) -> dict:
    result = _empty_result(raw)

    summary = str(
        data.get("incident_summary") or data.get("problem_summary") or ""
    ).strip()
    result["incident_summary"] = summary
    result["problem_summary"] = summary
    result["incident_type"] = str(data.get("incident_type") or "Unknown").strip()
    result["confidence"] = _coerce_confidence(data.get("confidence", 0))
    result["reasoning"] = str(data.get("reasoning") or "").strip()

    similar = data.get("similar_incidents") or data.get("matched_reports") or []
    for item in similar:
        if not isinstance(item, dict):
            continue
        incident = str(
            item.get("incident")
            or item.get("incident_id")
            or item.get("id")
            or ""
        ).strip()
        reason = str(item.get("reason") or "").strip()
        similarity = _coerce_similarity(item.get("similarity", 0))
        if incident or reason:
            entry = {
                "incident": incident or "unknown",
                "similarity": similarity,
                "reason": reason,
            }
            result["similar_incidents"].append(entry)
            result["matched_reports"].append({
                "incident_id": entry["incident"],
                "reason": reason,
                "similarity": similarity,
            })

    for idx, item in enumerate(data.get("recommended_resolution") or [], start=1):
        if not isinstance(item, dict):
            continue
        step = _parse_resolution_step(item, idx)
        if step:
            result["recommended_resolution"].append(step)

    for item in data.get("supporting_sql") or data.get("possible_sql") or []:
        sql = _sql_text(item)
        if sql:
            result["supporting_sql"].append(sql)
    result["possible_sql"] = list(result["supporting_sql"])

    for item in data.get("possible_tables") or []:
        if not isinstance(item, dict):
            continue
        table = str(item.get("table") or "").strip()
        if table:
            result["possible_tables"].append({
                "table": table,
                "reason": str(
                    item.get("reason") or item.get("evidence") or ""
                ).strip(),
            })

    alts = data.get("alternative_resolution") or []
    for alt in alts:
        if isinstance(alt, str) and alt.strip():
            result["alternative_resolution"].append(alt.strip())
        elif isinstance(alt, dict):
            text = str(alt.get("action") or alt.get("title") or "").strip()
            if text:
                result["alternative_resolution"].append(text)

    result["missing_information"] = [
        str(x).strip()
        for x in (data.get("missing_information") or [])
        if str(x).strip()
    ]
    result["notes"] = [
        str(x).strip()
        for x in (data.get("notes") or [])
        if str(x).strip()
    ]
    result["missing"] = list(result["missing_information"])
    result["warnings"] = list(result["notes"])

    result["steps"] = [
        {
            "num": s["step"],
            "action": s["action"],
            "tool": "Manual",
            "sql": None,
        }
        for s in result["recommended_resolution"]
    ]

    if not result["recommended_resolution"]:
        result["insufficient"] = True

    return result


def _parse_section_items(raw: str, label: str) -> list[str]:
    pattern = rf"{re.escape(label)}:\s*(.*?)(?:\n(?:{'|'.join(_SECTION_HEADERS)})\s*:|$)"
    match = re.search(pattern, raw, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    content = match.group(1).strip()
    for other in _SECTION_HEADERS:
        if other.upper() == label.upper():
            continue
        inline = re.search(rf"\s+{re.escape(other)}\s*:", content, re.IGNORECASE)
        if inline:
            content = content[: inline.start()].strip()

    if not content or content.lower() in _EMPTY_MARKERS:
        return []

    items: list[str] = []
    for line in content.splitlines():
        line = line.strip().lstrip("-• ").strip()
        if line and line.lower() not in _EMPTY_MARKERS:
            items.append(line)
    return items


def _parse_legacy_text(raw: str) -> dict:
    result = _empty_result(raw)

    if "INSUFFICIENT KNOWLEDGE BASE" in raw.upper():
        result["insufficient"] = True
        return result

    m = re.search(r"INCIDENT TYPE:\s*(.+)", raw, re.IGNORECASE)
    if m:
        result["incident_type"] = m.group(1).strip()

    steps_block = re.search(r"STEPS:\s*\n(.*?)(?:\n[A-Z]+:|$)", raw, re.DOTALL | re.IGNORECASE)
    if steps_block:
        for line in steps_block.group(1).splitlines():
            line = line.strip()
            m = re.match(
                r"(\d+)\.\s+(.+?)(?:\s*\|\s*TOOL:\s*(.+?))?(?:\s*\|\s*SQL:\s*(.+))?$",
                line,
                re.IGNORECASE,
            )
            if m:
                sql_raw = (m.group(4) or "").strip()
                sql = None if sql_raw.lower() in _EMPTY_MARKERS else sql_raw
                step_num = int(m.group(1))
                action = m.group(2).strip()
                step = {
                    "step": step_num,
                    "title": action,
                    "purpose": "",
                    "action": action,
                    "validation": "",
                    "evidence": [],
                }
                result["recommended_resolution"].append(step)
                result["steps"].append({
                    "num": step_num,
                    "action": action,
                    "tool": (m.group(3) or "Manual").strip(),
                    "sql": sql,
                })
                if sql:
                    result["supporting_sql"].append(sql)
                    result["possible_sql"].append(sql)

    result["warnings"] = _parse_section_items(raw, "WARNINGS")
    result["missing"] = _parse_section_items(raw, "MISSING")
    result["notes"] = list(result["warnings"])
    result["missing_information"] = list(result["missing"])
    result["incident_summary"] = result["incident_type"]
    result["problem_summary"] = result["incident_summary"]
    result["confidence"] = 70 if result["recommended_resolution"] else 20

    if not result["recommended_resolution"]:
        result["insufficient"] = True

    return result


def parse_resolution(raw: str) -> dict:
    if not raw or not raw.strip():
        return _empty_result(raw or "")

    data = _extract_json_blob(raw)
    if data is not None:
        return _normalize_from_json(data, raw)

    return _parse_legacy_text(raw)


def _confidence_badge(confidence: int) -> str:
    if confidence >= 75:
        return f"🟢 {confidence}% confidence"
    if confidence >= 50:
        return f"🟡 {confidence}% confidence"
    return f"🔴 {confidence}% confidence"


def render_guided_steps(parsed: dict):
    if parsed.get("insufficient"):
        st.warning(
            "The model returned no resolution steps. Check similar reports below "
            "or re-run with more context. Raw output is available at the bottom."
        )

    summary = parsed.get("incident_summary") or parsed.get("problem_summary")
    if summary:
        st.markdown(summary)

    confidence = parsed.get("confidence", 0)
    st.markdown(
        f"**Incident type:** `{parsed.get('incident_type', 'Unknown')}`  ·  "
        # f"{_confidence_badge(confidence)}"
    )

    if parsed.get("reasoning"):
        with st.expander("Engineering rationale", expanded=False):
            st.markdown(parsed["reasoning"])

    similar = parsed.get("similar_incidents") or []
    if not similar and parsed.get("matched_reports"):
        similar = [
            {
                "incident": r.get("incident_id", "unknown"),
                "similarity": r.get("similarity", 0),
                "reason": r.get("reason", ""),
            }
            for r in parsed["matched_reports"]
        ]

    if similar:
        with st.expander("Similar incidents cited", expanded=True):
            for inc in similar:
                sim = inc.get("similarity", 0)
                sim_label = f" ({sim}%)" if sim else ""
                st.markdown(
                    f"- **{inc.get('incident', 'unknown')}**{sim_label} — {inc.get('reason', '')}"
                )

    if parsed.get("missing_information"):
        st.error("**Missing information:**")
        for item in parsed["missing_information"]:
            st.markdown(f"- {item}")

    if parsed.get("notes"):
        st.warning("**Notes:**")
        for note in parsed["notes"]:
            st.markdown(f"- {note}")

    steps = parsed.get("recommended_resolution") or []
    if not steps:
        st.info("No structured steps in the response.")
        with st.expander("Raw LLM output", expanded=True):
            st.text(parsed.get("raw", ""))
        return

    st.divider()
    st.markdown(f"**{len(steps)} recommended steps:**")

    for step in steps:
        num = step.get("step", 0)
        title = step.get("title") or step.get("action", "")
        col_check, col_content = st.columns([0.06, 0.94])
        with col_check:
            st.checkbox(" ", key=f"step_{num}", label_visibility="collapsed")
        with col_content:
            st.markdown(f"**Step {num}: {title}**")
            if step.get("purpose"):
                st.caption(f"Purpose: {step['purpose']}")
            st.markdown(step.get("action", ""))
            if step.get("validation"):
                st.markdown(f"*Validate:* {step['validation']}")
            if step.get("evidence"):
                st.markdown(f"*Evidence:* {', '.join(step['evidence'])}")

    supporting_sql = parsed.get("supporting_sql") or parsed.get("possible_sql") or []
    if supporting_sql:
        st.divider()
        st.markdown("**Supporting SQL (from reports):**")
        for sql in supporting_sql:
            st.code(sql, language="sql")

    if parsed.get("alternative_resolution"):
        st.divider()
        st.markdown("**Alternative paths:**")
        for alt in parsed["alternative_resolution"]:
            st.markdown(f"- {alt}")

    if parsed.get("possible_tables"):
        with st.expander("Tables referenced", expanded=False):
            for entry in parsed["possible_tables"]:
                st.markdown(f"- `{entry['table']}` — {entry.get('reason', '')}")

    st.divider()
    st.caption("Tick each checkbox as you complete the step.")

    with st.expander("Raw LLM output", expanded=False):
        st.text(parsed.get("raw", ""))
