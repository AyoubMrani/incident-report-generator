"""
tests/test_hazard.py — irreversible operations must be visible as such.

Found live: asked to "just drop the production customers table", the assistant
returned `DROP TABLE production.customers;` as step 1, with no source, in the
same neutral styling as a documented fix. Low confidence was not enough — a
reader under incident pressure copies the command, not the badge.

The balance these tests hold: destructive commands are NOT suppressed (dropping
a corrupted table is genuinely the documented fix for some incidents), and the
patterns must not fire on ordinary work, or the warning becomes noise people
learn to click past.
"""

from __future__ import annotations

import json

import pytest

from app.chatbot.hazard import annotate_hazards, hazards_in


DANGEROUS = [
    "DROP TABLE production.customers;",
    "drop database billing;",
    "truncate table audit_log;",
    "delete from customers;",
    "UPDATE fm_opv SET status = '';",
    "rm -rf /var/log/app",
    "mkfs.ext4 /dev/sda1",
    "terraform destroy",
    "kubectl delete namespace prod",
    "helm uninstall billing",
    "git push origin main --force",
    "FLUSHALL",
    "revoke all on schema public from app_user;",
]

SAFE = [
    'select "homeId" from fm_opv where status = \'P\';',
    'UPDATE fm_opv SET "status" = \'\' WHERE "homeId" IN (\'A\') AND "status" = \'P\';',
    "delete from staging_dupes where batch_id = 'x';",
    "python menu.py",
    "kubectl rollout restart deployment/api",
    "kubectl delete pod api-7f9",
    "git push origin main --force-with-lease",
    "git push origin feature-branch",
    "select dedupe_cleanup.remove_duplicate_customers('cust_import');",
    "rm /tmp/lock",
    "helm upgrade billing ./chart",
]


@pytest.mark.parametrize("command", DANGEROUS)
def test_irreversible_commands_are_detected(command):
    assert hazards_in(command), command


@pytest.mark.parametrize("command", SAFE)
def test_ordinary_commands_are_not_flagged(command):
    """A warning that fires on routine work is a warning nobody reads."""
    assert not hazards_in(command), command


def test_a_scoped_delete_is_safe_but_an_unscoped_one_is_not():
    """The WHERE clause is the whole difference."""
    assert not hazards_in("delete from orders where id = 5;")
    assert hazards_in("delete from orders;")


def test_force_with_lease_is_not_flagged_but_bare_force_is():
    assert not hazards_in("git push --force-with-lease origin main")
    assert hazards_in("git push --force origin main")


def _answer(action: str) -> dict:
    return {"recommended_resolution": [
        {"step": 1, "title": "Do it", "action": action, "artifact": None}
    ]}


def test_an_ungrounded_hazard_is_marked_and_explained():
    parsed = _answer("DROP TABLE production.customers;")
    annotate_hazards(parsed, grounded=False)

    assert parsed["has_hazard"] is True
    assert parsed["hazard_ungrounded"] is True
    assert parsed["recommended_resolution"][0]["hazard_ungrounded"] is True
    assert "no incident report documents it" in parsed["additional_notes"].lower()


def test_a_grounded_hazard_is_marked_without_the_ungrounded_warning():
    """Dropping a table can be the documented fix; say so, don't cry wolf."""
    parsed = _answer("DROP TABLE staging.corrupt_import;")
    annotate_hazards(parsed, grounded=True)

    assert parsed["has_hazard"] is True
    assert parsed["hazard_ungrounded"] is False
    assert "no incident report documents it" not in parsed["additional_notes"].lower()


def test_a_harmless_answer_carries_no_hazard_flags():
    parsed = _answer("select 1;")
    annotate_hazards(parsed, grounded=True)

    assert parsed["has_hazard"] is False
    assert parsed["hazards"] == []
    assert "hazard" not in parsed["recommended_resolution"][0]


def test_hazards_hidden_in_an_artifact_are_found():
    """The command usually lives in the artifact, not the prose."""
    parsed = {"recommended_resolution": [{
        "step": 1, "title": "Clean up", "action": "run the cleanup",
        "artifact": {"language": "sql", "content": "TRUNCATE TABLE customers;"},
    }]}
    annotate_hazards(parsed, grounded=False)

    assert parsed["has_hazard"] is True


def test_annotating_an_empty_answer_is_safe():
    parsed = {"recommended_resolution": []}
    annotate_hazards(parsed, grounded=True)
    assert parsed["has_hazard"] is False


# ── the grounded path, end to end through the real pipeline ───────────────────
#
# Unit tests above call annotate_hazards() directly. These build a real
# knowledge base from a report that documents a destructive fix, retrieve it,
# and shape a model answer through _shape() — so the grounded branch is
# exercised by the same machinery that runs in production, not by hand-passing
# `grounded=True`. The shipped corpus documents no destructive commands, which
# is why this fixture exists rather than a live_check case.


def _destructive_report(directory):
    import json as _json

    (directory / "INC7001_Purge corrupt import staging table.json").write_text(
        _json.dumps({
            "metadata": {
                "incident_id": "INC7001",
                "title": "Purge corrupt import staging table",
                "category": "Data Quality",
                "subcategory": "Cleanup",
            },
            "blocks": [
                {"id": "b1", "type": "paragraph", "title": "Root Cause",
                 "content": "A failed overnight import left staging_import in a "
                            "partially written state; rows cannot be repaired in "
                            "place because the batch id column was never written."},
                {"id": "b2", "type": "code", "title": "Fix", "items": [{
                    "id": "c1", "type": "code", "title": "Purge and reload",
                    "header": "Purge the staging table, then re-run the import",
                    "language": "sql",
                    "content": "TRUNCATE TABLE staging_import;",
                }]},
            ],
        }),
        encoding="utf-8",
    )


def test_a_documented_destructive_fix_is_flagged_but_not_called_ungrounded(
        tmp_path, monkeypatch):
    """Truncating a corrupt staging table is a real documented remediation.

    It must still carry the irreversible warning — but not the "nobody has run
    this here" escalation, which is what separates a documented procedure from
    something the model invented.
    """
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _destructive_report(reports)

    from app.chatbot.retrieval import search_multimodal
    from app.chatbot.selection import select_sources
    from app.chatbot.service import ChatbotService
    from app.chatbot.ingestion import build_knowledge_base

    kb = build_knowledge_base(reports)
    query = "purge the corrupt import staging table"
    hits = search_multimodal(query, None, kb.embed_model, kb.embeddings,
                             kb.documents, kb.metadata, top_k=5, bm25=kb.bm25)
    results = select_sources(query, hits)
    assert results, "the fixture report should be retrievable"

    svc = ChatbotService(kb, None)
    shaped = svc._shape(json.dumps({
        "incident_summary": "Corrupt staging table must be purged and reloaded.",
        "confidence": 85,
        "root_cause": "Partially written import.",
        "recommended_resolution": [{
            "step": 1, "action_type": "SQL_QUERY",
            "title": "Purge the staging table",
            "action": "Run TRUNCATE TABLE staging_import;",
            "artifact": {"language": "sql", "title": "",
                         "content": "TRUNCATE TABLE staging_import;"},
        }],
    }), results, None)

    assert shaped["has_hazard"] is True
    assert shaped["hazard_ungrounded"] is False
    assert "empties a table" in shaped["hazards"]
    assert "no incident report documents it" not in \
        shaped["additional_notes"].lower()
    # A documented fix keeps its confidence: the warning is a caution, not a
    # downgrade, or people would learn to distrust correct guidance.
    assert shaped["confidence"] >= 80


def test_the_same_command_ungrounded_gets_the_stronger_warning(tmp_path, monkeypatch):
    """Identical command, no supporting report -> escalated wording."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))

    from app.chatbot.service import ChatbotService

    svc = ChatbotService(object(), None)
    shaped = svc._shape(json.dumps({
        "incident_summary": "Purge it.",
        "confidence": 85,
        "recommended_resolution": [{
            "step": 1, "action_type": "SQL_QUERY", "title": "Purge",
            "action": "Run TRUNCATE TABLE staging_import;",
            "artifact": {"language": "sql", "title": "",
                         "content": "TRUNCATE TABLE staging_import;"},
        }],
    }), [], None)

    assert shaped["has_hazard"] is True
    assert shaped["hazard_ungrounded"] is True
    assert "no incident report documents it" in shaped["additional_notes"].lower()
