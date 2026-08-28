"""
chatbot/resolution.py — parse expert JSON resolutions from the LLM.

Ported from incident_chatbot/resolution.py, keeping only the parsing/normalizing
half (parse_resolution, format_retrieval_context, and helpers). The Streamlit
`render_guided_steps` renderer was dropped: the React frontend renders the parsed
resolution dict now. This module is pure — dict in, dict out, no I/O, no UI.
"""

import json
import re
from collections.abc import Callable
from functools import lru_cache



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
        "artifacts": [],
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
        # Report sections (Problem Summary / Root Cause / Investigation /
        # Resolution / Validation / Notes) and gate outcomes.
        "root_cause": "",
        "investigation": "",
        "validation": "",
        "additional_notes": "",
        "has_media": False,
        "no_documented_resolution": False,
        "ai_suggestion": "",
        "refused": False,
        "raw": raw,
    }


# The solution types a resolution step can be classified as. A single report
# legitimately mixes several of these in sequence (e.g. extract with SQL, then
# run a script), so each step carries its own type rather than the whole
# resolution being labelled once.
ACTION_TYPES = (
    "SQL_QUERY",
    "CODE",
    "CONFIG_CHANGE",
    "INFRA_ACTION",
    "INVESTIGATION_MEDIA",
    "LOG_ANALYSIS",
    "MANUAL_PROCEDURE",
    "DOC_REFERENCE",
)

# Fallback when the model omits or invents a type: infer from the step's
# artifact language, else treat it as a manual procedure (never assume SQL).
_LANG_TO_TYPE = {
    "sql": "SQL_QUERY",
    "bash": "CODE", "sh": "CODE", "shell": "CODE", "python": "CODE",
    "powershell": "CODE", "javascript": "CODE", "typescript": "CODE", "java": "CODE",
    "yaml": "CONFIG_CHANGE", "json": "CONFIG_CHANGE", "xml": "CONFIG_CHANGE",
    "ini": "CONFIG_CHANGE", "hcl": "CONFIG_CHANGE", "dockerfile": "CONFIG_CHANGE",
    "log": "LOG_ANALYSIS",
}


def _normalize_action_type(value, artifact_language: str = "") -> str:
    """Coerce a model-supplied action_type onto the known set."""
    candidate = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if candidate in ACTION_TYPES:
        return candidate
    inferred = _LANG_TO_TYPE.get((artifact_language or "").strip().lower())
    return inferred or "MANUAL_PROCEDURE"


# How a full document is fetched. Defaults to the filesystem; the app swaps in
# a storage-backed reader at startup when reports live in object storage, so
# resolution reads the same source retrieval indexed rather than a local
# directory that may not hold the report at all.
_document_reader: "Callable[[str], str] | None" = None


def set_document_reader(reader: "Callable[[str], str] | None") -> None:
    """Install the function that turns a chunk's `path` into raw text.

    Called once during startup. Clearing the cache matters: documents already
    read through the previous reader would otherwise survive the swap and mask
    the new backend entirely.
    """
    global _document_reader
    _document_reader = reader
    _read_full_document.cache_clear()


@lru_cache(maxsize=256)
def _read_full_document(path: str) -> str:
    """Re-extract a report's complete text (cached).

    Retrieval indexes fixed-size chunks, but answering faithfully needs the
    whole procedure. Reading the source again gives the full text without
    inflating the index.
    """
    try:
        from .ingestion import _read_json, _read_json_text, _read_md

        if _document_reader is not None:
            raw = _document_reader(path)
            if not raw:
                return ""
            return _read_json_text(raw) if path.endswith(".json") else raw

        if path.endswith(".json"):
            return _read_json(path)
        if path.endswith((".md", ".txt")):
            return _read_md(path)
    except Exception:  # noqa: BLE001 — fall back to the chunk on any failure
        return ""
    return ""


def _full_document_text(chunk: dict) -> str:
    """Full text of the report this chunk came from, if it can be re-read."""
    path = str(chunk.get("path") or "")
    if not path:
        return ""
    # Prefer the .json source even when the .md mirror was the chunk that
    # matched: the JSON carries the structured blocks, so image markers and
    # per-block titles survive, whereas the markdown rendering loses them.
    if path.endswith(".md"):
        from_json = _read_full_document(path[:-3] + ".json")
        if from_json:
            return from_json
    return _read_full_document(path)


_SQL_START = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE|ALTER|MERGE)\b",
    re.IGNORECASE,
)
# A candidate is only accepted as SQL if it also contains clause structure —
# "with a list of Home IDs ...; " reads like a statement start but is prose.
_SQL_STRUCTURE = re.compile(r"\b(FROM|INTO|SET|VALUES|WHERE|JOIN)\b", re.IGNORECASE)
_SHELL_LINE = re.compile(
    r"^\s*(?:\$\s*)?((?:sudo\s+)?(?:python[0-9.]*|bash|sh|kubectl|docker|helm|"
    r"curl|systemctl|psql|git|cd|export|ssh|scp|tail|grep|awk|sed)\b.*)$",
    re.IGNORECASE | re.MULTILINE,
)


_RESOLUTION_MARKERS = re.compile(
    r"(resolution\s+steps?|steps?\s+taken|remediation|fix\s+applied|"
    r"how\s+(it\s+was|we)\s+(fixed|resolved)|workaround|procedure)\s*:",
    re.IGNORECASE,
)


def report_documents_resolution(hit: dict) -> bool:
    """True when a report actually documents how the incident was fixed.

    Used to overrule a model that claims "no documented resolution" about a
    report whose text plainly contains one — that is a property of the source,
    not a judgement call.
    """
    text = _full_document_text(hit) or str(hit.get("text") or "")
    if not text:
        return False
    if _RESOLUTION_MARKERS.search(text):
        return True
    # A report carrying a runnable query or command documents a fix even when
    # it lacks an explicit "Resolution Steps:" heading.
    return bool(extract_code_blocks(hit))


def extract_code_blocks(hit: dict) -> list[dict]:
    """Recover the code/queries a report actually documents, from its own text.

    Returns [{language, title, content}] in document order. Used to restore
    statements the model referenced but did not reproduce faithfully, so the
    answer shows the source's real query/command rather than an elided stub.
    """
    text = _full_document_text(hit) or str(hit.get("text") or "")
    if not text:
        return []

    blocks: list[dict] = []

    # SQL: from a statement keyword to its terminating semicolon. Nested
    # subqueries would each match, so keep only outermost statements — skip any
    # match that starts inside a statement already captured.
    consumed_until = -1
    for match in _SQL_START.finditer(text):
        start = match.start()
        if start < consumed_until:
            continue  # inside a statement we already took (a subquery)
        end = text.find(";", start)
        if end == -1:
            continue
        statement = text[start : end + 1].strip()
        # Guard against a stray keyword in prose matching a far-away semicolon:
        # require real clause structure, not just a leading keyword.
        if 40 <= len(statement) <= 4000 and _SQL_STRUCTURE.search(statement):
            blocks.append({"language": "sql", "title": "Query from the report",
                           "content": statement})
            consumed_until = end

    # Shell/Python invocations, de-duplicated, in order.
    seen: set[str] = set()
    commands: list[str] = []
    for match in _SHELL_LINE.finditer(text):
        cmd = match.group(1).strip().rstrip(".")
        if 4 <= len(cmd) <= 300 and cmd not in seen:
            seen.add(cmd)
            commands.append(cmd)
    if commands:
        lang = "python" if any(c.startswith("python") for c in commands) else "bash"
        blocks.append({"language": lang, "title": "Commands from the report",
                       "content": "\n".join(commands)})

    return blocks


def format_retrieval_context(
    results: list[dict], limit: int = 5, max_chars_per_chunk: int = 900
) -> str:
    """Format retrieval hits with scores for the resolution prompt.

    Each chunk's CONTENT is capped (max_chars_per_chunk) so the prompt stays
    lean — generation latency scales with prompt size, and the tail of a long
    chunk rarely changes the answer.
    """
    blocks: list[str] = []
    for chunk in results[:limit]:
        raw_score = chunk.get("semantic_score", chunk.get("score", 0))
        score_pct = int(float(raw_score) * 100)
        # Prefer the FULL source document over the matched chunk. Retrieval
        # matches a single ~700-char window, but a resolution procedure usually
        # spans several (extract with SQL, then run a script, then verify);
        # sending only the matched window truncates the answer mid-procedure.
        content = _full_document_text(chunk) or str(chunk.get("text", ""))
        if len(content) > max_chars_per_chunk:
            content = content[:max_chars_per_chunk].rstrip() + " …"
        blocks.append(
            "\n".join([
                f"RETRIEVAL_SIMILARITY: {score_pct}%",
                f"INCIDENT_ID: {chunk.get('incident_id') or 'unknown'}",
                f"TITLE: {chunk.get('title', '')}",
                f"SOURCE: {chunk.get('source', '')}",
                f"CONTENT:\n{content}",
            ])
        )
    return "\n\n---\n\n".join(blocks)


def _extract_json_blob(raw: str) -> dict | None:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    start = text.find("{")
    if start == -1:
        return None
    end = text.rfind("}")
    if end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Salvage a truncated response. Generation can stop mid-object when the
    # token budget runs out, which would otherwise discard an answer that was
    # almost entirely complete. Close the open string/containers and re-parse so
    # the steps produced before the cut-off survive.
    return _parse_truncated_json(text[start:])


def _parse_truncated_json(text: str) -> dict | None:
    """Best-effort parse of a JSON object whose tail was cut off."""
    in_string = False
    escaped = False
    stack: list[str] = []

    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()

    repaired = text
    if in_string:
        repaired += '"'
    # Drop a dangling key/comma that has no value yet, e.g. '"notes": '
    repaired = re.sub(r',\s*"[^"]*"\s*:\s*$', "", repaired.rstrip())
    repaired = repaired.rstrip().rstrip(",")
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"

    try:
        data = json.loads(repaired)
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


def _is_placeholder(text: str) -> bool:
    """True for schema filler the model echoed instead of real content ('...')."""
    stripped = (text or "").strip().strip(".…").strip()
    return not stripped


# A stub the model emits when it knows a query belongs here but not which one:
# "SELECT ...", "UPDATE ...;". Unrunnable, and dangerous to present as a step.
_STUB_SNIPPET = re.compile(
    r"^\s*(?:select|update|delete|insert|alter|drop|create)\b[\s\S]{0,20}?"
    r"(?:\.\.\.|…)[\s;]*$",
    re.IGNORECASE,
)


def _is_stub_snippet(text: str) -> bool:
    """True for a code artifact that is only a keyword plus an ellipsis."""
    return bool(_STUB_SNIPPET.match(text or ""))


def _parse_resolution_step(item: dict, default_step: int) -> dict | None:
    action = str(item.get("action") or "").strip()
    title = str(item.get("title") or action or "").strip()
    if not action and not title:
        return None
    # Drop schema placeholders rather than rendering "..." as an instruction.
    if _is_placeholder(action):
        action = ""
    if _is_placeholder(title):
        return None

    evidence = item.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    evidence = [str(e).strip() for e in evidence if str(e).strip()]

    # Optional per-step artifact (query, script, config, or log excerpt).
    artifact = None
    raw_artifact = item.get("artifact")
    if isinstance(raw_artifact, dict):
        content = str(raw_artifact.get("content") or "").strip()
        if content:
            artifact = {
                "language": str(raw_artifact.get("language") or "text").strip().lower(),
                "title": str(raw_artifact.get("title") or "").strip(),
                "content": content,
            }

    return {
        "step": _coerce_int(item.get("step"), default_step),
        "action_type": _normalize_action_type(
            item.get("action_type"), artifact["language"] if artifact else ""
        ),
        "title": title,
        "purpose": _clean_field(item.get("purpose")),
        "action": action or title,
        "validation": _clean_field(item.get("validation")),
        "evidence": evidence,
        "artifact": artifact,
    }


def _as_text(value) -> str:
    """Prose for a field the model may have returned as a list or scalar."""
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        text = " ".join(parts)
    else:
        text = str(value or "").strip()
    return "" if _is_placeholder(text) else text


def _clean_field(value) -> str:
    """A stripped field value, blank when it is only schema filler."""
    text = str(value or "").strip()
    return "" if _is_placeholder(text) else text


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

    # Report sections and gate outcomes. Models sometimes return a list where
    # the schema asks for prose, so normalize either shape to readable text.
    result["root_cause"] = _as_text(data.get("root_cause"))
    result["investigation"] = _as_text(data.get("investigation"))
    result["validation"] = _as_text(data.get("validation"))
    result["additional_notes"] = _as_text(data.get("additional_notes"))
    result["has_media"] = bool(data.get("has_media"))
    result["refused"] = bool(data.get("refused"))
    result["no_documented_resolution"] = bool(data.get("no_documented_resolution"))
    result["ai_suggestion"] = str(data.get("ai_suggestion") or "").strip()

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
            # Surface a step's artifact in the top-level list too, so consumers
            # that read `artifacts` (report synthesis, legacy UI) still see it.
            if step.get("artifact"):
                a = step["artifact"]
                result["artifacts"].append({
                    "language": a["language"],
                    "title": a["title"] or step["title"],
                    "content": a["content"],
                })

    # Typed artifacts (new): each {language, title, content}. The model now
    # picks the right language (bash, python, java, yaml, sql, ...) per incident.
    for item in data.get("artifacts") or []:
        if isinstance(item, dict):
            content = str(item.get("content") or "").strip()
            if content:
                result["artifacts"].append({
                    "language": str(item.get("language") or "text").strip().lower(),
                    "title": str(item.get("title") or "").strip(),
                    "content": content,
                })
        elif isinstance(item, str) and item.strip():
            result["artifacts"].append(
                {"language": "text", "title": "", "content": item.strip()}
            )

    # Backward compat: older responses / reports used supporting_sql. Treat those
    # as SQL-typed artifacts so nothing is lost.
    for item in data.get("supporting_sql") or data.get("possible_sql") or []:
        sql = _sql_text(item)
        if sql:
            result["supporting_sql"].append(sql)
            result["artifacts"].append({"language": "sql", "title": "", "content": sql})
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

    # Honor an explicit insufficient flag from the model (it decided it cannot
    # safely diagnose), OR infer it when no concrete steps were produced.
    if data.get("insufficient") is True or not result["recommended_resolution"]:
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


