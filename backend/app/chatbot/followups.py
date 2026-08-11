"""
chatbot/followups.py — "what to ask next", generated on demand.

Deliberately not part of the main resolution pipeline. `ChatbotService.answer`
already runs one LLM call per turn at 11-25s on the local model (see
eval/model_bench.py); chaining a second call onto every answer would double
that for a feature most turns never use. This is triggered by a user action
(POST /api/chat/followups) instead, so the cost is paid only when someone
actually wants suggestions — the default chat path is untouched.

The prompt is intentionally narrow: given the question and the answer that
was already produced, propose short next questions *this same assistant could
actually answer* — not generic conversation starters. It sees no report text
and does no retrieval, so it stays fast and cannot introduce new ungrounded
claims; it is proposing questions, not answers.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict

from app.shared.llm.provider import LLMProvider

from .resolution import _extract_json_blob

# Small and separate from the main answer cache (service.py's ANSWER_CACHE_SIZE):
# suggestions are cheap to hold and keyed on different input (question+answer
# summary rather than the full retrieval prompt), so sharing one cache would
# mean one eviction policy fighting two different value sizes and hit rates.
_CACHE_SIZE = 200

FOLLOWUP_PROMPT = """\
You suggest follow-up questions for an IT incident assistant. You are not \
answering the incident — only proposing what the user might reasonably ask \
next, in this same chat, about the SAME incident.

Rules:
- Propose exactly 3 short questions (max 12 words each), most useful first.
- Each must be answerable by re-querying this assistant about the incident \
below — not a generic "anything else?" prompt, and not a question already \
answered in the summary.
- Ground them in specifics from the question/answer (the service, error, \
table, or step actually mentioned) rather than generic incident-response \
advice ("how do I prevent this in general").
- If the answer already covers root cause, resolution steps, and validation \
completely, it is fine to propose questions about edge cases, rollback, or \
a related system instead of restating what is already there.
- Return JSON only, no markdown fences, no prose: {{"questions": ["...", "...", "..."]}}

Original question:
{question}

Assistant's answer (summary):
{answer_summary}
"""

# One line per field the prompt is fed, so the summary stays well under the
# question itself in size — this call must stay cheap.
_MAX_SUMMARY_CHARS = 900
_MAX_QUESTION_WORDS = 12


def _answer_summary(answer: dict) -> str:
    """Compress a stored answer dict into the few lines the prompt needs.

    Deliberately excludes SQL/code artifacts and full step text: they bloat
    the prompt without helping the model propose *questions*, and keeping them
    out means this call never re-transmits (and can't leak) a full runnable
    procedure into a differently-purposed prompt.
    """
    parts: list[str] = []
    if answer.get("incident_type"):
        parts.append(f"Type: {answer['incident_type']}")
    if answer.get("incident_summary"):
        parts.append(f"Summary: {answer['incident_summary']}")
    if answer.get("root_cause"):
        parts.append(f"Root cause: {answer['root_cause']}")
    steps = answer.get("recommended_resolution") or []
    if steps:
        titles = ", ".join(s.get("title", "") for s in steps if s.get("title"))
        parts.append(f"Resolution steps covered: {titles}")
    if answer.get("validation"):
        parts.append(f"Validation: {answer['validation']}")

    text = "\n".join(parts) or "(no structured answer available)"
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[:_MAX_SUMMARY_CHARS].rstrip() + " …"
    return text


def _clean_questions(raw: list) -> list[str]:
    """Keep well-formed, short, non-duplicate questions; drop the rest.

    A model that ignores the "3 questions" instruction or produces a 40-word
    run-on is more common on a 3B local model than on a hosted one, so this
    is enforced rather than trusted.
    """
    seen: set[str] = set()
    out: list[str] = []
    for q in raw:
        if not isinstance(q, str):
            continue
        q = re.sub(r"\s+", " ", q).strip().strip("\"'")
        # A little over the prompt's own 12-word ask is tolerated (models don't
        # count precisely), but this is a filter against a model that ignored
        # the instruction altogether and returned a paragraph.
        if not q or len(q.split()) > _MAX_QUESTION_WORDS:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        if not q.endswith("?"):
            q += "?"
        out.append(q)
        if len(out) == 3:
            break
    return out


def parse_followups(raw: str) -> list[str]:
    """Parse the model's JSON response into a clean question list.

    Never raises: a malformed or empty response yields `[]`, which the caller
    treats as "no suggestions available" rather than an error — this feature
    degrading to nothing is fine, since it is opt-in and additive.
    """
    data = _extract_json_blob(raw)
    if not isinstance(data, dict):
        return []
    questions = data.get("questions")
    # A string is iterable in Python, so `"not a list" or []` would pass this
    # straight into _clean_questions and yield one "question" per character.
    if not isinstance(questions, list):
        return []
    return _clean_questions(questions)


class FollowupSuggester:
    """Generates follow-up questions for a previously-produced answer.

    Holds its own small cache rather than sharing ChatbotService's: this is
    keyed on (question, answer) and called from a different endpoint, so
    coupling its lifecycle to the main answer cache (which is invalidated on
    every reindex) would drop follow-up suggestions for unrelated reasons.
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._cache: "OrderedDict[str, list[str]]" = OrderedDict()
        self._lock = threading.Lock()

    def _key(self, question: str, answer: dict) -> str:
        basis = question.strip() + " " + _answer_summary(answer)
        return hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()

    def suggest(self, question: str, answer: dict) -> list[str]:
        key = self._key(question, answer)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return list(hit)

        prompt = FOLLOWUP_PROMPT.format(
            question=question.strip()[:500],
            answer_summary=_answer_summary(answer),
        )
        raw = self.provider.chat(prompt)
        questions = parse_followups(raw)

        with self._lock:
            self._cache[key] = list(questions)
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)
        return questions
