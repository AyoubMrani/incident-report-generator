"""
tests/test_grounding.py — answers may only contain what the evidence supports.

Two failure modes these lock down, both observed live with llama3.2:3b:

  * cross-contamination — a command documented in one incident ("python menu.py")
    reappears in an unrelated answer. Running it against production is exactly
    the harm the assistant exists to prevent.
  * stub snippets — "SELECT ..." rendered as if it were a runnable query.

Plus the ingestion invariants that decide *which* report an answer is attributed
to: its declared id and its human title.
"""

from __future__ import annotations

import json

from app.chatbot.ingestion import (
    _declared_incident_id,
    _get_report_title,
    _read_json,
    build_knowledge_base,
)
from app.chatbot.resolution import _is_stub_snippet
from app.chatbot.service import _strip_ungrounded_artifacts


# ── helpers ───────────────────────────────────────────────────────────────────


def _step(content: str, language: str = "sql") -> dict:
    return {"title": "step", "artifact": {"language": language, "content": content}}


def _evidence(text: str) -> list[dict]:
    return [{"text": text, "path": "", "source": "reports/x.json"}]


# ── ungrounded artifacts ──────────────────────────────────────────────────────


def test_artifact_absent_from_evidence_is_stripped():
    """The live bug: 'python menu.py' bled in from a different incident."""
    parsed = {"recommended_resolution": [_step("python menu.py", "bash")]}
    _strip_ungrounded_artifacts(parsed, _evidence(
        "select dedupe_cleanup.remove_duplicate_customers('cust_import');"
    ))
    assert parsed["recommended_resolution"][0]["artifact"] is None


def test_artifact_present_in_evidence_is_kept():
    sql = "select dedupe_cleanup.remove_duplicate_customers('cust_import');"
    parsed = {"recommended_resolution": [_step(sql)]}
    _strip_ungrounded_artifacts(parsed, _evidence(f"Stored function invocation {sql}"))
    assert parsed["recommended_resolution"][0]["artifact"]["content"] == sql


def test_same_artifact_is_kept_or_stripped_depending_on_the_evidence():
    """Grounding is contextual, not a blocklist: menu.py is legitimate here."""
    parsed = {"recommended_resolution": [_step("python menu.py", "bash")]}
    _strip_ungrounded_artifacts(parsed, _evidence("Run the rollback: python menu.py"))
    assert parsed["recommended_resolution"][0]["artifact"] is not None


def test_stub_snippet_is_stripped_even_when_keyword_is_grounded():
    parsed = {"recommended_resolution": [_step("SELECT ...")]}
    _strip_ungrounded_artifacts(parsed, _evidence("SELECT id FROM circuits"))
    assert parsed["recommended_resolution"][0]["artifact"] is None


def test_stripping_is_skipped_when_there_is_no_evidence():
    """With nothing retrieved there is nothing to check against; leave it alone."""
    parsed = {"recommended_resolution": [_step("python menu.py", "bash")]}
    _strip_ungrounded_artifacts(parsed, [])
    assert parsed["recommended_resolution"][0]["artifact"] is not None


def test_steps_without_artifacts_are_untouched():
    parsed = {"recommended_resolution": [{"title": "Call the DBA", "artifact": None}]}
    _strip_ungrounded_artifacts(parsed, _evidence("anything"))
    assert parsed["recommended_resolution"][0]["title"] == "Call the DBA"


def test_stub_snippet_detection():
    for stub in ["SELECT ...", "select …", "UPDATE ...;", "  DELETE ... "]:
        assert _is_stub_snippet(stub), stub
    for real in [
        "SELECT id FROM circuits WHERE status != 'OOS'",
        "select dedupe_cleanup.remove_duplicate_customers('x');",
        "python menu.py",
    ]:
        assert not _is_stub_snippet(real), real


# ── report identity ───────────────────────────────────────────────────────────


def _write(directory, name: str, payload: dict) -> str:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_declared_id_wins_over_a_referenced_incident(tmp_path):
    """A report that links a related ticket must not be filed under that ticket."""
    path = _write(tmp_path, "INC1048202_Yellow Duplicate Cleanup.json", {
        "metadata": {"incident_id": "INC1048202", "title": "Yellow Duplicate Cleanup"},
        "blocks": [{"type": "incident_example", "incident_id": "INC1048301"}],
    })
    assert _declared_incident_id(path) == "INC1048202"


def test_title_comes_from_metadata_not_the_extracted_prose(tmp_path):
    """_get_report_title receives extracted prose; it must still find the title."""
    path = _write(tmp_path, "INC1048202_Yellow Duplicate Cleanup.json", {
        "metadata": {"incident_id": "INC1048202", "title": "Yellow Duplicate Cleanup"},
        "blocks": [{"type": "paragraph", "content": "body"}],
    })
    assert _get_report_title(path, _read_json(path)) == "Yellow Duplicate Cleanup"


def test_title_falls_back_to_the_filename_when_metadata_has_none(tmp_path):
    path = _write(tmp_path, "INC1048202_Yellow Duplicate Cleanup.json", {
        "metadata": {"incident_id": "INC1048202"},
        "blocks": [{"type": "paragraph", "content": "body"}],
    })
    assert _get_report_title(path, _read_json(path)) == "Yellow Duplicate Cleanup"


# ── duplicate .md / .json twins ───────────────────────────────────────────────


def test_md_twin_of_a_json_report_is_not_indexed_twice(tmp_path, monkeypatch):
    """Both twins would make one incident compete with itself for source slots."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write(reports, "INC1.json", {
        "metadata": {"incident_id": "INC1", "title": "Duplicate Cleanup"},
        "blocks": [{"type": "paragraph", "content": "remove duplicate rows"}],
    })
    (reports / "INC1.md").write_text("# Duplicate Cleanup\nremove duplicate rows",
                                     encoding="utf-8")

    kb = build_knowledge_base(reports)
    sources = {m["source"] for m in kb.metadata}

    assert any(s.endswith("INC1.json") for s in sources)
    assert not any(s.endswith("INC1.md") for s in sources)


def test_a_standalone_md_report_is_still_indexed(tmp_path, monkeypatch):
    """Only mirrored .md files are skipped — an .md-only report must survive."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write(reports, "INC1.json", {
        "metadata": {"incident_id": "INC1", "title": "A"},
        "blocks": [{"type": "paragraph", "content": "alpha"}],
    })
    (reports / "INC2.md").write_text("# Standalone\nbeta content", encoding="utf-8")

    sources = {m["source"] for m in build_knowledge_base(reports).metadata}
    assert any(s.endswith("INC2.md") for s in sources)
