"""
chatbot/hazard.py — flag irreversible operations in a proposed resolution.

An incident assistant genuinely needs to surface destructive commands: dropping
a corrupted table or truncating a runaway log really is the documented fix for
some incidents, and hiding that would make the tool useless. The danger is
narrower and specific — a destructive command the model *invented*, presented
in the same neutral styling as one traced to a report that a human already ran
against this estate.

So this does not refuse and does not rewrite. It marks each step, and the
answer as a whole, so the UI can warn and the reader can tell "this is what
INC1048202 did" from "the model thinks this might work". Ungrounded hazards are
escalated: those are the ones nobody has validated here.
"""

from __future__ import annotations

import re

# Operations that cannot be undone by re-running them. Kept deliberately tight:
# a pattern that fires on ordinary work would train people to ignore the badge.
_HAZARDS: tuple[tuple[str, str], ...] = (
    (r"\bdrop\s+(table|database|schema|index|user|role)\b", "drops a database object"),
    (r"\btruncate\s+table\b", "empties a table"),
    (r"\bdelete\s+from\b(?![\s\S]{0,200}\bwhere\b)", "deletes every row (no WHERE)"),
    (r"\bupdate\s+\w[\w.\"]*\s+set\b(?![\s\S]{0,200}\bwhere\b)",
     "updates every row (no WHERE)"),
    (r"\brm\s+(-[a-z]*[rf][a-z]*\s+)+", "recursively removes files"),
    (r"\bmkfs(\.\w+)?\b", "formats a filesystem"),
    (r"\bdd\s+[^\n]*\bof=/dev/", "writes directly to a device"),
    (r"\b(kubectl|oc)\s+delete\s+(namespace|pvc|persistentvolumeclaim)\b",
     "deletes a namespace or persistent volume"),
    (r"\bhelm\s+(delete|uninstall)\b", "uninstalls a release"),
    (r"\bterraform\s+destroy\b", "destroys infrastructure"),
    # --force-with-lease is the guarded variant and is not flagged: it refuses
    # when the remote moved, which is exactly the accident being warned about.
    (r"\bgit\s+push\s+[^\n]*--force(?!-with-lease)\b",
     "force-pushes over remote history"),
    (r"\bflushall\b|\bflushdb\b", "clears the whole cache"),
    (r"\bdrop\s+partition\b", "drops a partition"),
    (r"\brevoke\s+all\b", "revokes all privileges"),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), label) for p, label in _HAZARDS)


def hazards_in(text: str) -> list[str]:
    """Human-readable labels for every irreversible operation in `text`."""
    if not text:
        return []
    found: list[str] = []
    for pattern, label in _COMPILED:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


def _step_text(step: dict) -> str:
    """Everything in a step a command could hide in."""
    artifact = step.get("artifact") or {}
    return " \n".join(
        str(part) for part in (
            step.get("action"), step.get("title"), step.get("purpose"),
            artifact.get("content"),
        ) if part
    )


def annotate_hazards(parsed: dict, grounded: bool) -> None:
    """Mark destructive steps in place, and summarise on the answer.

    `grounded` says whether the answer came from a selected report. An
    ungrounded destructive command is the serious case: nobody has run it here,
    so it is marked `hazard_ungrounded` for the UI to treat more loudly.
    """
    labels: list[str] = []
    for step in parsed.get("recommended_resolution") or []:
        found = hazards_in(_step_text(step))
        if not found:
            continue
        step["hazard"] = found
        step["hazard_ungrounded"] = not grounded
        for label in found:
            if label not in labels:
                labels.append(label)

    parsed["hazards"] = labels
    parsed["has_hazard"] = bool(labels)
    parsed["hazard_ungrounded"] = bool(labels) and not grounded
    if labels:
        note = (
            "This procedure contains irreversible operations ("
            + "; ".join(labels)
            + ")."
        )
        if not grounded:
            note += (
                " No incident report documents it — it comes from the model's "
                "general knowledge, not from a fix anyone has run on this "
                "estate. Verify against a backup and a change ticket first."
            )
        else:
            note += " Confirm you are on the intended environment before running it."
        existing = (parsed.get("additional_notes") or "").strip()
        parsed["additional_notes"] = f"{note} {existing}".strip()
