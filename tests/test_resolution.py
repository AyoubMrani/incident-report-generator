import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from incident_chatbot.resolution import format_retrieval_context, parse_resolution


EXPERT_JSON = """{
  "incident_summary": "Defective port flags remain after field repair.",
  "incident_type": "Defective Port Cleanup",
  "confidence": 0.82,
  "similar_incidents": [
    {"incident": "INC0383918", "similarity": 0.79, "reason": "Same D-status removal"}
  ],
  "recommended_resolution": [
    {
      "step": 1,
      "title": "Identify affected OPV rows",
      "purpose": "Scope cleanup",
      "action": "Query fm_opv for homes still showing D status",
      "validation": "Row count matches ticket attachment",
      "evidence": ["INC0383918"]
    },
    {
      "step": 2,
      "title": "Clear D status",
      "purpose": "Remove defective port marker",
      "action": "Update fm_opv status for affected home IDs",
      "validation": "No D flag remains",
      "evidence": ["INC0383918"]
    },
    {
      "step": 3,
      "title": "Document in ServiceNow",
      "purpose": "Audit trail",
      "action": "Add work notes with homes cleaned",
      "validation": "Ticket notes updated",
      "evidence": []
    }
  ],
  "supporting_sql": [
    "SELECT * FROM fm_opv WHERE homeId IN (...);"
  ],
  "reasoning": "Pattern matches prior defective port cleanups.",
  "alternative_resolution": ["Escalate if COMA still shows stale status"]
}"""


def test_parse_expert_resolution_json():
    parsed = parse_resolution(EXPERT_JSON)

    assert parsed["incident_summary"].startswith("Defective port")
    assert parsed["confidence"] == 82
    assert len(parsed["recommended_resolution"]) == 3
    assert parsed["recommended_resolution"][0]["title"] == "Identify affected OPV rows"
    assert parsed["similar_incidents"][0]["incident"] == "INC0383918"
    assert parsed["similar_incidents"][0]["similarity"] == 79
    assert parsed["supporting_sql"][0].startswith("SELECT")
    assert parsed["reasoning"]
    assert len(parsed["alternative_resolution"]) == 1
    assert parsed["insufficient"] is False


def test_format_retrieval_context_includes_scores():
    ctx = format_retrieval_context([
        {
            "score": 0.87,
            "incident_id": "INC0383918",
            "title": "Remove Defective Port Status",
            "source": "reports/x.md",
            "text": "Clear D status in fm_opv",
        }
    ])
    assert "RETRIEVAL_SIMILARITY: 87%" in ctx
    assert "INC0383918" in ctx


def test_parse_json_inside_markdown_fence_with_nested_objects():
    raw = """```json
{
  "incident_summary": "Duplicate OPV cleanup",
  "incident_type": "Duplicate Record Cleanup",
  "confidence": 65,
  "similar_incidents": [],
  "recommended_resolution": [
    {
      "step": 1,
      "title": "Find duplicates",
      "purpose": "Scope",
      "action": "Query support tables",
      "validation": "Count matches ticket",
      "evidence": []
    }
  ],
  "supporting_sql": [],
  "reasoning": "General duplicate cleanup pattern",
  "alternative_resolution": []
}
```"""
    parsed = parse_resolution(raw)
    assert parsed["incident_summary"] == "Duplicate OPV cleanup"
    assert len(parsed["recommended_resolution"]) == 1
    assert parsed["insufficient"] is False


def test_parse_legacy_nri_json_still_works():
    raw = """{
  "problem_summary": "Provision cleanup",
  "incident_type": "Provision Cleanup",
  "confidence": 70,
  "matched_reports": [{"incident_id": "INC1", "reason": "test"}],
  "recommended_resolution": [{"step": 1, "action": "Remove P status"}],
  "possible_sql": [],
  "missing_information": [],
  "notes": []
}"""
    parsed = parse_resolution(raw)
    assert parsed["incident_summary"] == "Provision cleanup"
    assert parsed["matched_reports"][0]["incident_id"] == "INC1"


def test_empty_steps_marks_insufficient():
    raw = """{
  "incident_summary": "x",
  "incident_type": "Unknown",
  "confidence": 10,
  "similar_incidents": [],
  "recommended_resolution": [],
  "supporting_sql": [],
  "reasoning": "",
  "alternative_resolution": []
}"""
    parsed = parse_resolution(raw)
    assert parsed["insufficient"] is True


def test_parse_resolution_legacy_text_format():
    raw = """INCIDENT TYPE: Remove Defective Port Status

STEPS:
1. Clear the D flag in fm_opv | TOOL: SQL | SQL: UPDATE fm_opv SET status = '' WHERE id IN (...)

WARNINGS: none
MISSING: none"""
    parsed = parse_resolution(raw)
    assert len(parsed["recommended_resolution"]) == 1
    assert parsed["supporting_sql"][0].startswith("UPDATE fm_opv")
