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
