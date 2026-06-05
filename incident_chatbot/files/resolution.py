"""
resolution.py

Two responsibilities:
  1. parse_resolution(raw)  — turn the LLM's structured text output into a dict
  2. render_guided_steps()  — display it as an interactive checklist in Streamlit

No domain-specific logic here. Everything is driven by what the LLM returns,
which in turn is driven by what the knowledge base contains.
"""

import re
import streamlit as st


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_resolution(raw: str) -> dict:
    """
    Parse the structured output from RESOLUTION_PROMPT into a clean dict.

    Expected format from the LLM:
        INCIDENT TYPE: <text>

        STEPS:
        1. <action> | TOOL: <tool> | SQL: <query or none>
        2. ...

        WARNINGS:
        - <text>

        MISSING:
        - <text>

    Returns:
        {
            "incident_type": str,
            "steps": [{"num": int, "action": str, "tool": str, "sql": str|None}],
            "warnings": [str],
            "missing": [str],
            "insufficient": bool,
        }
    """
    result = {
        "incident_type": "Unknown",
        "steps": [],
        "warnings": [],
        "missing": [],
        "insufficient": False,
        "raw": raw,
    }

    if "INSUFFICIENT KNOWLEDGE BASE" in raw.upper():
        result["insufficient"] = True
        return result

    # Incident type
    m = re.search(r"INCIDENT TYPE:\s*(.+)", raw, re.IGNORECASE)
    if m:
        result["incident_type"] = m.group(1).strip()

    # Steps block
    steps_block = re.search(r"STEPS:\s*\n(.*?)(?:\n[A-Z]+:|$)", raw, re.DOTALL | re.IGNORECASE)
    if steps_block:
        for line in steps_block.group(1).splitlines():
            line = line.strip()
            # Match: "1. action | TOOL: x | SQL: y"
            m = re.match(r"(\d+)\.\s+(.+?)(?:\s*\|\s*TOOL:\s*(.+?))?(?:\s*\|\s*SQL:\s*(.+))?$", line, re.IGNORECASE)
            if m:
                sql_raw = (m.group(4) or "").strip()
                sql = None if sql_raw.lower() in ("none", "", "-", "n/a") else sql_raw
                result["steps"].append({
                    "num":    int(m.group(1)),
                    "action": m.group(2).strip(),
                    "tool":   (m.group(3) or "Manual").strip(),
                    "sql":    sql,
                })

    # Warnings block
    warnings_block = re.search(r"WARNINGS:\s*\n(.*?)(?:\n[A-Z]+:|$)", raw, re.DOTALL | re.IGNORECASE)
    if warnings_block:
        for line in warnings_block.group(1).splitlines():
            line = line.strip().lstrip("-• ").strip()
            if line:
                result["warnings"].append(line)

    # Missing block
    missing_block = re.search(r"MISSING:\s*\n(.*?)(?:\n[A-Z]+:|$)", raw, re.DOTALL | re.IGNORECASE)
    if missing_block:
        for line in missing_block.group(1).splitlines():
            line = line.strip().lstrip("-• ").strip()
            if line:
                result["missing"].append(line)

    return result


# ── Renderer ──────────────────────────────────────────────────────────────────

def render_guided_steps(parsed: dict):
    """
    Render the parsed resolution as a guided interactive checklist.

    Each step shows:
      - A checkbox the operator ticks when done
      - The action description
      - The tool to use (as a small badge)
      - The SQL query in a copyable code block (if present)
    Warnings and missing info are shown as callouts above the steps.
    """

    if parsed.get("insufficient"):
        st.warning(
            "The knowledge base does not contain enough information to generate "
            "a verified resolution for this incident type. "
            "Check the similar reports below or escalate."
        )
        return

    # Incident type banner
    st.markdown(
        f"**Incident type:** `{parsed['incident_type']}`",
    )

    # Missing information callout — show first so operator knows what to gather
    if parsed.get("missing"):
        with st.container():
            st.error("⚠️ Missing information — gather this before starting:")
            for item in parsed["missing"]:
                st.markdown(f"- {item}")

    # Warnings callout
    if parsed.get("warnings"):
        with st.container():
            st.warning("**Before you start — read these warnings:**")
            for w in parsed["warnings"]:
                st.markdown(f"- {w}")

    st.divider()

    steps = parsed.get("steps", [])
    if not steps:
        st.info("No structured steps were returned. See the raw output below.")
        with st.expander("Raw LLM output"):
            st.text(parsed.get("raw", ""))
        return

    st.markdown(f"**{len(steps)} steps to complete:**")

    # Tool badge colors
    TOOL_COLORS = {
        "sql":           "#1e40af",
        "dbeaver":       "#1e40af",
        "function call": "#065f46",
        "excel":         "#14532d",
        "manual":        "#78350f",
        "servicenow":    "#7c3aed",
    }

    for step in steps:
        col_check, col_content = st.columns([0.06, 0.94])

        with col_check:
            st.checkbox(
                "",
                key=f"step_{step['num']}",
                label_visibility="collapsed",
            )

        with col_content:
            tool_key   = step["tool"].lower()
            tool_color = TOOL_COLORS.get(tool_key, "#374151")

            # Tool badge inline with action
            badge = (
                f'<span style="'
                f'background:{tool_color};color:#fff;'
                f'font-size:11px;font-weight:600;'
                f'padding:2px 8px;border-radius:4px;'
                f'margin-left:8px;vertical-align:middle'
                f'">{step["tool"].upper()}</span>'
            )
            st.markdown(
                f'**Step {step["num"]}:** {step["action"]} {badge}',
                unsafe_allow_html=True,
            )

            if step.get("sql"):
                st.code(step["sql"], language="sql")

    st.divider()
    st.caption("Tick each checkbox as you complete the step.")

    # Collapsible raw output for debugging
    with st.expander("Raw LLM output", expanded=False):
        st.text(parsed.get("raw", ""))
