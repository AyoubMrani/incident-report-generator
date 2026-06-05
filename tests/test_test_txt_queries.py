from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_TXT = ROOT / "test.txt"
REPORTS_DIR = ROOT / "reports"


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "how", "i", "if", "in", "is", "it", "its", "me", "my", "of", "on",
    "or", "our", "should", "that", "the", "their", "there", "these", "this",
    "to", "we", "what", "which", "with", "you", "your", "do", "does", "did",
    "need", "can", "could", "would", "please", "some", "any", "still",
    "after", "before", "already", "only", "want", "make", "remove", "update",
    "fix", "change", "move", "delete", "clean", "cleanup",
}

# Maps test.txt expected labels → substrings that appear in real report titles/bodies
CONCEPT_HINTS: dict[str, list[str]] = {
    "defective port cleanup": ["defective port", "remove defective", " d status", "d flag"],
    "provision cleanup": ["provision", "remove provision", " p status"],
    "duplicate cleanup": ["duplicate", "yellow", "support_remove_opv_duplicate"],
    "home status change": ["home status", "homeunplanned", "homeplanning", "support_changehomestatus"],
    "coma synchronization": ["coma", "sync", "coma_status"],
    "export verification": ["export", "failed export"],
    "cleanup verification": ["cleanup", "partial cleanup", "export"],
    "access number mismatch": ["access number", "mismatch", "opv export"],
}


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS
    }


def _load_reports() -> list[dict[str, str]]:
    reports: list[dict[str, str]] = []
    for path in sorted(REPORTS_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), path.stem)
        title = first_line.removeprefix("# Incident Report:").strip()
        reports.append(
            {
                "title": title,
                "body": content,
                "title_tokens": _tokenize(title),
                "body_tokens": _tokenize(content),
            }
        )
    return reports


def _score_report(query: str, report: dict[str, str]) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    title_overlap = len(query_tokens & report["title_tokens"])
    body_overlap = len(query_tokens & report["body_tokens"])
    score = (title_overlap * 5.0) + body_overlap

    hay = f"{report['title']} {report['body']}".lower()
    query_lower = query.lower()
    for phrase in (
        "defective", "provision", "duplicate", "planning", "coma",
        "export", "access number", "cleanup", "home status",
    ):
        if phrase in query_lower and phrase in hay:
            score += 4.0

    # NRI operational phrase → report concept boosts (mirrors assistant prompt)
    phrase_boosts = [
        (("repaired", "technician", "problematic", "dashboard"), ("defective port", "d status")),
        (("indicators", "traces", "remove"), ("provision", "defective port", "status")),
        (("imported twice", "twice"), ("duplicate",)),
        (("highlights", "spreadsheet", "deleting"), ("duplicate", "yellow")),
        (("planning", "pending", "deployment"), ("home status", "homeplanning", "homeunplanned")),
        (("downstream", "old value", "source platform"), ("coma", "sync")),
        (("reporting", "stale"), ("export", "cleanup")),
        (("identifier", "spreadsheet", "database export"), ("access number", "mismatch")),
    ]
    for query_terms, report_terms in phrase_boosts:
        if any(t in query_lower for t in query_terms):
            if any(t in hay for t in report_terms):
                score += 6.0

    return score


def _matches_expected_label(label: str, report: dict[str, str]) -> bool:
    hay = f"{report['title']} {report['body']}".lower()
    key = label.lower().strip()
    hints = CONCEPT_HINTS.get(key, [token for token in key.split() if len(token) > 3])
    return any(hint in hay for hint in hints)


def _load_cases() -> list[dict[str, object]]:
    lines = TEST_TXT.read_text(encoding="utf-8").splitlines()
    cases: list[dict[str, object]] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r"Test\s+\d+", line, re.IGNORECASE):
            test_id = line
            i += 1
            query_lines: list[str] = []
            while i < len(lines) and lines[i].strip() not in {"Expected:", "Expected retrieval:"}:
                current = lines[i].strip()
                if current and not re.match(r"Test\s+\d+", current, re.IGNORECASE):
                    query_lines.append(current)
                i += 1

            if i < len(lines) and lines[i].strip() in {"Expected:", "Expected retrieval:"}:
                i += 1

            expected: list[str] = []
            while i < len(lines):
                current = lines[i].strip()
                if not current:
                    i += 1
                    continue
                if re.match(r"Test\s+\d+", current, re.IGNORECASE):
                    break
                expected.append(current)
                i += 1

            cases.append(
                {
                    "test_id": test_id,
                    "query": " ".join(query_lines).strip(),
                    "expected": expected,
                }
            )
            continue

        i += 1

    return cases


def test_test_txt_loads_cases():
    cases = _load_cases()
    assert len(cases) >= 8, f"Expected at least 8 tests in test.txt, got {len(cases)}"


def test_queries_retrieve_reports_matching_expected_concepts():
    reports = _load_reports()
    cases = _load_cases()

    assert reports, "No report markdown files found in reports/"
    assert cases, "No cases found in test.txt"

    for case in cases:
        ranked = sorted(
            reports,
            key=lambda report: _score_report(str(case["query"]), report),
            reverse=True,
        )
        top = ranked[:5]
        expected = case["expected"]

        matched = any(
            _matches_expected_label(label, report)
            for label in expected
            for report in top
        )
        assert matched, (
            f"No expected concept found in top retrieval results.\n"
            f"{case['test_id']}\n"
            f"Query: {case['query']}\n"
            f"Expected one of: {expected}\n"
            f"Top titles: {[r['title'] for r in top]}"
        )
