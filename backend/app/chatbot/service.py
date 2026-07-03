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

from app.shared.llm.provider import LLMProvider

from .config import CONFIDENCE_THRESHOLD, RESOLUTION_CONTEXT_K, TOP_K
from .ingestion import KnowledgeBase, build_knowledge_base
from .intent import Intent, canned_reply, classify
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
    format_retrieval_context,
    parse_resolution,
)
from .retrieval import combine_retrieval_queries, search_multimodal
from .security import injection_scan, wrap_untrusted

# How many prior turns of a conversation to feed back into the resolution prompt
# for follow-up context ("what SQL for that?"). Kept small to bound prompt size.
MEMORY_TURNS = 4


def _chat_reply(text: str) -> dict:
    """A non-incident, conversational reply shaped like the pipeline's dict.

    Same keys the API/streaming layer reads, but with is_chat=True and no
    retrieval, so greetings/smalltalk render as a plain chat bubble.
    """
    return {
        "is_chat": True,
        "incident_summary": text,
        "incident_type": "Assistant",
        "confidence": 100,
        "recommended_resolution": [],
        "supporting_sql": [],
        "matched_reports": [],
        "matched_report_ids": [],
        "retrieval": [],
        "low_confidence": False,
        "raw": text,
    }


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
    ) -> dict:
        """Route intent, apply security, understand + retrieve, build the prompt.

        Returns either a short-circuit chat reply (intent != incident) or the
        pieces the LLM step needs: prompt, retrieval results, injection note.
        """
        intent = classify(query, has_image=bool(image_b64))
        if intent is not Intent.INCIDENT:
            # Greeting / smalltalk / meta: reply as a chatbot, no LLM, no search.
            return {"short_circuit": _chat_reply(canned_reply(intent))}

        # Security: flag prompt-injection so the user text is fenced as untrusted
        # data and we can surface a note. (We never obey instructions in it.)
        scan = injection_scan(query)

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
        )

        # Build the resolution prompt: prior-turn memory + untrusted-fenced input.
        problem = combine_retrieval_queries(text_query or query, image_query or None)
        problem = _history_block(history) + wrap_untrusted(problem)
        image_analysis = image_query or NO_IMAGE_ANALYSIS

        if results:
            prompt = format_prompt(
                RESOLUTION_PROMPT,
                RESOLUTION_PROMPT_REQUIRED,
                problem=problem,
                image_analysis=image_analysis,
                # Feed only the top few chunks into the prompt (latency); all
                # retrieved hits still surface as sources in _shape().
                knowledge=format_retrieval_context(results, limit=RESOLUTION_CONTEXT_K),
            )
        else:
            prompt = format_prompt(
                FALLBACK_PROMPT,
                FALLBACK_PROMPT_REQUIRED,
                problem=problem,
                image_analysis=image_analysis,
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
        parsed["low_confidence"] = (
            parsed.get("confidence", 0) / 100.0 < CONFIDENCE_THRESHOLD
        )
        parsed["is_chat"] = False
        if injection is not None and injection.detected:
            parsed["security_note"] = injection.note
        return parsed

    # ── blocking answer ───────────────────────────────────────────────────────

    def answer(
        self,
        query: str,
        image_b64: str | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        """Run the full pipeline and return a structured resolution dict."""
        prep = self._prepare(query, image_b64, history)
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
    ) -> Iterator[dict]:
        """Yield streaming events for SSE.

        Event shapes:
          {"type": "chat",  "text": ...}                 (greeting/smalltalk/meta)
          {"type": "token", "text": ...}                 (incremental LLM output)
          {"type": "done",  "answer": <structured dict>} (final parsed result)
        """
        prep = self._prepare(query, image_b64, history)
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


def _source_link(hit: dict) -> dict:
    """Turn a retrieval hit into a citation the UI can open in-app.

    `source` looks like 'reports/INC1048301_Foo.json'. We expose the bare
    filename and the API route that returns that report's JSON, so a click opens
    the cited report inside the app (report viewer) without leaving the chat.
    Only .json reports are openable in-app; .md/.docx hits carry a null open_url.
    """
    source = hit.get("source") or ""
    filename = source.split("/")[-1] if source else ""
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
