"""
chatbot/service.py — the chatbot pipeline as one headless service.

This is what ui.py orchestrated in Streamlit, extracted into a plain object:

    understand text (+ optional screenshot)
        -> hybrid retrieval over the shared reports KB
        -> expert-resolution LLM call
        -> parse into a structured dict the frontend renders

The KnowledgeBase and LLMProvider are built once (in the app lifespan) and held
here, so a request is just: run the pipeline. No global/session state.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.shared.llm.provider import LLMProvider

from .config import CONFIDENCE_THRESHOLD, RESOLUTION_CONTEXT_K, TOP_K
from .ingestion import KnowledgeBase, build_knowledge_base
from .intent import Intent, canned_reply, classify, has_incident_signal
from .llm import understand_screenshot
from .prompts import (
    FALLBACK_PROMPT,
    FALLBACK_PROMPT_REQUIRED,
    NO_IMAGE_ANALYSIS,
    RESOLUTION_PROMPT,
    RESOLUTION_PROMPT_REQUIRED,
    format_prompt,
)
from .resolution import (
    extract_code_blocks,
    format_retrieval_context,
    parse_resolution,
    report_documents_resolution,
)
from .retrieval import combine_retrieval_queries, search_multimodal
from .selection import select_sources
from .security import injection_scan, wrap_untrusted

# How many prior turns of a conversation to feed back into the resolution prompt
# for follow-up context ("what SQL for that?"). Kept small to bound prompt size.
MEMORY_TURNS = 4

# A selected report scoring at or above this (retrieval score + entity overlap,
# where overlap alone maxes at 1.0) is a direct match: its title/entities line up
# with the query, not merely its topic.
STRONG_MATCH_SCORE = 0.60
# Floor applied to such an answer when it also produced grounded steps.
STRONG_MATCH_CONFIDENCE = 80


def _chat_reply(text: str, *, needs_clarification: bool = False) -> dict:
    """A non-incident, conversational reply shaped like the pipeline's dict.

    Same keys the API/streaming layer reads, but with is_chat=True and no
    retrieval, so greetings/smalltalk render as a plain chat bubble.
    `needs_clarification` marks the "too vague to diagnose" abstention so the UI
    can style it as a prompt for more info rather than a normal chat reply.
    """
    return {
        "is_chat": True,
        "needs_clarification": needs_clarification,
        "incident_summary": text,
        "incident_type": "Needs more info" if needs_clarification else "Assistant",
        "confidence": 0 if needs_clarification else 100,
        "recommended_resolution": [],
        "artifacts": [],
        "supporting_sql": [],
        "matched_reports": [],
        "matched_report_ids": [],
        "retrieval": [],
        "low_confidence": needs_clarification,
        "root_cause": "",
        "investigation": "",
        "validation": "",
        "additional_notes": "",
        "has_media": False,
        "no_documented_resolution": False,
        "ai_suggestion": "",
        "refused": False,
        "raw": text,
    }


def _refusal_reply() -> dict:
    """Gate 2 refusal: brief, firm, no explanation of what triggered it."""
    reply = _chat_reply(
        "I can't do that. I'm restricted to helping with incident reports and "
        "resolutions — happy to help if you've got an incident to look into."
    )
    reply["refused"] = True
    reply["incident_type"] = "Out of scope"
    return reply


def _history_block(history: list[dict] | None) -> str:
    """Render prior turns as a short transcript for follow-up context."""
    if not history:
        return ""
    lines = []
    for turn in history[-MEMORY_TURNS:]:
        role = turn.get("role", "")
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        who = "User" if role == "user" else "Assistant"
        lines.append(f"{who}: {text}")
    if not lines:
        return ""
    return "Earlier in this conversation:\n" + "\n".join(lines) + "\n\n"


def _corrections_block(corrections: list[dict] | None) -> str:
    """Render learned human corrections so past feedback steers the answer.

    Each correction is {question, correction}. These carry high authority: a
    human said "the right answer to this kind of question is X", so the prompt
    tells the model to prefer them when the current incident matches.
    """
    if not corrections:
        return ""
    lines = [
        "LEARNED CORRECTIONS from past human feedback — if the current incident "
        "matches one of these, follow the corrected guidance:",
    ]
    for c in corrections:
        q = (c.get("question") or "").strip()
        fix = (c.get("correction") or "").strip()
        if fix:
            lines.append(f"- For a question like \"{q[:120]}\": {fix}")
    return "\n".join(lines) + "\n\n"


class ChatbotService:
    """Holds the KB + provider; answers incident questions."""

    def __init__(self, knowledge_base: KnowledgeBase, provider: LLMProvider):
        self.kb = knowledge_base
        self.provider = provider

    @classmethod
    def build(cls, reports_dir, provider: LLMProvider) -> "ChatbotService":
        """Construct by indexing ``reports_dir`` once. Call this in the lifespan."""
        kb = build_knowledge_base(reports_dir)
        return cls(kb, provider)

    # ── shared preparation (everything up to the LLM call) ────────────────────

    def _prepare(
        self,
        query: str,
        image_b64: str | None,
        history: list[dict] | None,
        corrections: list[dict] | None = None,
    ) -> dict:
        """Route intent, apply security, understand + retrieve, build the prompt.

        Returns either a short-circuit chat reply (intent != incident) or the
        pieces the LLM step needs: prompt, retrieval results, injection note.

        `corrections` are learned human corrections (from thumbs-down feedback)
        relevant to this query; they are injected into the prompt so past fixes
        influence future answers.
        """
        intent = classify(query, has_image=bool(image_b64), has_history=bool(history))
        if intent is Intent.CLARIFY:
            # Incident-flavored but too vague: ask for specifics, do NOT guess.
            return {"short_circuit": _chat_reply(canned_reply(intent),
                                                 needs_clarification=True)}
        if intent is not Intent.INCIDENT:
            # Greeting / smalltalk / meta: reply as a chatbot, no LLM, no search.
            return {"short_circuit": _chat_reply(canned_reply(intent))}

        # Gate 2 — injection / jailbreak. Flag it so the user text is fenced as
        # untrusted data downstream. If the message is ONLY an injection attempt
        # (no diagnosable incident content), refuse outright and stop; if a real
        # incident merely contains such phrasing, continue and attach the note.
        scan = injection_scan(query)
        if scan.detected and not has_incident_signal(query):
            # The message is ONLY an injection attempt — no diagnosable incident
            # content to serve. Refuse briefly and stop.
            return {"short_circuit": _refusal_reply()}

        # Understand:
        #   - TEXT: skip the extra LLM rephrase call. The embedding model
        #     retrieves fine on the raw query, and that call was ~half the total
        #     latency for little gain. Use the raw query directly.
        #   - IMAGE: still run the vision model — a screenshot genuinely needs to
        #     be turned into text before it can be embedded/searched.
        text_query = query.strip()
        image_query = (
            understand_screenshot(image_b64, self.provider) if image_b64 else ""
        )

        # Retrieve: hybrid search over the shared reports KB.
        results = search_multimodal(
            text_query or query,
            image_query or None,
            self.kb.embed_model,
            self.kb.embeddings,
            self.kb.documents,
            self.kb.metadata,
            top_k=TOP_K,
            bm25=self.kb.bm25,   # fuse lexical BM25 with vector search (RRF)
        )

        # Gate 3 — select only the reports that genuinely answer the question.
        # Topically-similar-but-wrong candidates are discarded here so they can
        # neither contribute resolution steps nor appear as cited sources.
        results = select_sources(text_query or query, results)

        # Build the resolution prompt: prior-turn memory + untrusted-fenced input.
        problem = combine_retrieval_queries(text_query or query, image_query or None)
        problem = _history_block(history) + wrap_untrusted(problem)
        image_analysis = image_query or NO_IMAGE_ANALYSIS

        corrections_block = _corrections_block(corrections)

        if results:
            prompt = format_prompt(
                RESOLUTION_PROMPT,
                RESOLUTION_PROMPT_REQUIRED,
                problem=problem,
                image_analysis=image_analysis,
                corrections=corrections_block,
                # Gate 3 already narrowed this to the reports that genuinely
                # match (at most MAX_SELECTED), so every one of them goes into
                # the prompt in full — the model must be able to reproduce a
                # matching report's complete documented resolution.
                # Each selected report is passed in FULL (its whole document,
                # not just the chunk that matched), so a multi-step procedure —
                # extract with SQL, run a script, verify — survives intact.
                knowledge=format_retrieval_context(
                    results, limit=len(results), max_chars_per_chunk=6000
                ),
            )
        else:
            prompt = format_prompt(
                FALLBACK_PROMPT,
                FALLBACK_PROMPT_REQUIRED,
                problem=problem,
                image_analysis=image_analysis,
                corrections=corrections_block,
            )

        return {"prompt": prompt, "results": results, "injection": scan}

    def _shape(self, raw: str, results: list[dict], injection) -> dict:
        """Parse the LLM output and add the API-facing fields."""
        parsed = parse_resolution(raw)

        matched = [
            m["incident_id"]
            for m in parsed.get("matched_reports", [])
            if m.get("incident_id")
        ]
        if not matched:
            matched = [r["incident_id"] for r in results if r.get("incident_id")]

        parsed["retrieval"] = [_source_link(r) for r in results]
        parsed["matched_report_ids"] = matched

        # Contradiction guard: an answer cannot both claim no documented
        # resolution exists AND present resolution steps. When the model does
        # both, the steps win — they came from a selected report — so the
        # misleading "nothing documented" banner is dropped.
        if parsed.get("no_documented_resolution") and parsed.get("recommended_resolution"):
            parsed["no_documented_resolution"] = False

        # The model also claims "nothing documented" about reports that plainly
        # document a fix — it does this when the query wording differs from the
        # report's. Whether a report documents a resolution is a property of the
        # report, not a judgement call, so check the source directly.
        if parsed.get("no_documented_resolution") and any(
            report_documents_resolution(r) for r in results
        ):
            parsed["no_documented_resolution"] = False

        # Restore any query/command the model referenced but did not reproduce
        # faithfully, taking it from the selected report itself.
        _recover_artifacts(parsed, results)

        # Drop invented citations. Models copy the example ids out of the schema
        # in the prompt, so a step can claim evidence from a report that was
        # never retrieved. Only ids actually present in the selected reports may
        # be cited.
        _strip_invented_evidence(parsed, results)

        # Confidence floor. Small local models routinely under-report confidence
        # (a short query or an unfamiliar id format makes them hedge) even when
        # they were handed a report that directly matches and documents the fix.
        # Match quality is something we measured during selection, so trust that
        # over the model's self-assessment: if a strongly-matching report was
        # selected and the model produced grounded steps from it, the answer is
        # not low-confidence.
        if results:
            top_score = float(results[0].get("selection_score") or 0.0)
            grounded = bool(parsed.get("recommended_resolution")) or any(
                report_documents_resolution(r) for r in results
            )
            if top_score >= STRONG_MATCH_SCORE and grounded:
                parsed["confidence"] = max(parsed.get("confidence", 0), STRONG_MATCH_CONFIDENCE)

        parsed["low_confidence"] = (
            parsed.get("confidence", 0) / 100.0 < CONFIDENCE_THRESHOLD
        )
        parsed["is_chat"] = False
        parsed["needs_clarification"] = bool(parsed.get("insufficient"))

        # A grounded answer with real steps is never an "insufficient" abstention.
        if parsed.get("recommended_resolution"):
            parsed["needs_clarification"] = False

        if injection is not None and injection.detected:
            parsed["security_note"] = injection.note
        return parsed

    # ── blocking answer ───────────────────────────────────────────────────────

    def answer(
        self,
        query: str,
        image_b64: str | None = None,
        history: list[dict] | None = None,
        corrections: list[dict] | None = None,
    ) -> dict:
        """Run the full pipeline and return a structured resolution dict."""
        prep = self._prepare(query, image_b64, history, corrections)
        if "short_circuit" in prep:
            return prep["short_circuit"]
        raw = self.provider.chat(prep["prompt"])
        return self._shape(raw, prep["results"], prep["injection"])

    # ── streaming answer ──────────────────────────────────────────────────────

    def answer_stream(
        self,
        query: str,
        image_b64: str | None = None,
        history: list[dict] | None = None,
        corrections: list[dict] | None = None,
    ) -> Iterator[dict]:
        """Yield streaming events for SSE.

        Event shapes:
          {"type": "chat",  "text": ...}                 (greeting/smalltalk/meta)
          {"type": "token", "text": ...}                 (incremental LLM output)
          {"type": "done",  "answer": <structured dict>} (final parsed result)
        """
        prep = self._prepare(query, image_b64, history, corrections)
        if "short_circuit" in prep:
            reply = prep["short_circuit"]
            yield {"type": "chat", "text": reply["raw"]}
            yield {"type": "done", "answer": reply}
            return

        chunks: list[str] = []
        for piece in self.provider.chat_stream(prep["prompt"]):
            chunks.append(piece)
            yield {"type": "token", "text": piece}

        raw = "".join(chunks)
        yield {"type": "done", "answer": self._shape(raw, prep["results"], prep["injection"])}


def _recover_artifacts(parsed: dict, results: list[dict]) -> None:
    """Attach source code/queries the model referenced but failed to reproduce.

    Small local models are unreliable at copying a long query verbatim: they
    abbreviate it ("SELECT ...") or drop it entirely. The statement is sitting in
    the selected report, so rather than trusting the copy, we take it from the
    source and attach it to the step that calls for it. This keeps the answer
    faithful without depending on the model's transcription.
    """
    if not results or not parsed.get("recommended_resolution"):
        return

    # Pull code/query blocks out of the top selected report.
    blocks = extract_code_blocks(results[0])
    if not blocks:
        return

    used: set[int] = set()
    for step in parsed["recommended_resolution"]:
        art = step.get("artifact")
        content = (art or {}).get("content", "").strip() if art else ""
        # A missing artifact, or an elided placeholder like "SELECT ...".
        needs_recovery = (
            art is None
            or len(content) < 40
            or content.rstrip().endswith(("...", "…"))
        )
        if not needs_recovery:
            continue

        wanted_lang = (art or {}).get("language") or _language_hint(step)
        for i, block in enumerate(blocks):
            if i in used:
                continue
            if wanted_lang and block["language"] != wanted_lang:
                continue
            step["artifact"] = dict(block)
            used.add(i)
            break

    # Keep the top-level artifacts list in sync with what the steps now carry.
    step_arts = [
        s["artifact"] for s in parsed["recommended_resolution"] if s.get("artifact")
    ]
    seen: set[str] = set()
    merged: list[dict] = []
    for a in step_arts + list(parsed.get("artifacts") or []):
        key = a["content"].strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(a)
    parsed["artifacts"] = merged


def _strip_invented_evidence(parsed: dict, results: list[dict]) -> None:
    """Remove cited incident ids that are not in the selected reports."""
    real_ids = {
        str(r.get("incident_id")).strip().lower()
        for r in results
        if r.get("incident_id")
    }
    for step in parsed.get("recommended_resolution") or []:
        evidence = step.get("evidence") or []
        step["evidence"] = [
            e for e in evidence if str(e).strip().lower() in real_ids
        ]
    # Same for the similar-incidents list and the report-id summary.
    parsed["similar_incidents"] = [
        s for s in (parsed.get("similar_incidents") or [])
        if str(s.get("incident", "")).strip().lower() in real_ids
    ]
    parsed["matched_report_ids"] = [
        m for m in (parsed.get("matched_report_ids") or [])
        if str(m).strip().lower() in real_ids
    ]


def _language_hint(step: dict) -> str:
    """Guess the artifact language a step is asking for, from its own words."""
    text = f"{step.get('title','')} {step.get('action','')}".lower()
    action_type = (step.get("action_type") or "").upper()
    if action_type == "SQL_QUERY" or "query" in text or "sql" in text:
        return "sql"
    if action_type == "CODE" or "script" in text or "python" in text or "run " in text:
        return "python" if "python" in text else "bash"
    return ""


def _source_link(hit: dict) -> dict:
    """Turn a retrieval hit into a citation the UI can open in-app.

    `source` looks like 'reports/INC1048301_Foo.json'. We expose the bare
    filename and the API route that returns that report's JSON, so a click opens
    the cited report inside the app (report viewer) without leaving the chat.
    A hit on a report's markdown mirror is re-pointed at its JSON sibling, which
    is the openable, image-bearing version; other non-JSON hits (e.g. .docx)
    carry a null open_url.
    """
    source = hit.get("source") or ""
    filename = source.split("/")[-1] if source else ""

    if filename.endswith(".md"):
        json_name = filename[:-3] + ".json"
        path = str(hit.get("path") or "")
        # Only re-point when the sibling actually exists on disk.
        if path.endswith(".md") and Path(path[:-3] + ".json").exists():
            filename = json_name

    open_url = (
        f"/api/reports/content/{filename}"
        if filename.endswith(".json")
        else None
    )
    return {
        "incident_id": hit.get("incident_id"),
        "title": hit.get("title"),
        "source": source,
        "filename": filename or None,
        "open_url": open_url,
        "score": hit.get("score"),
    }
