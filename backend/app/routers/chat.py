"""
routers/chat.py — HTTP surface for the chatbot module.

Two concerns:
  1. The chat pipeline (POST /api/chat) — delegates to the ChatbotService.
  2. Persistent conversations — CRUD over the SQLite ChatStore so history
     survives restarts and syncs across a client's tabs.

Identity comes from the verified OIDC subject in the bearer token (see
`app/auth`). With `AUTH_DISABLED=1` it falls back to the old `X-Client-Id`
header, which is how the test suite and a Keycloak-less dev run work. Either
way it reaches the store as one opaque id, so the store queries are unchanged —
which is exactly what the pre-auth design predicted.

Returns 503 for the pipeline when the chatbot didn't initialise; conversation
CRUD still works (it only needs the store), so history is browsable even if
Ollama is down.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import (
    AuthContext,
    auth_disabled,
    current_user,
    require_admin,
)
from app.chatbot.security import redact
from app.shared.llm.provider import LLMUnavailable
from app.shared.logging import get_logger

log = get_logger("app.routers.chat")

# Auth declared at the router so it runs *before* request-body validation.
# Without it an unauthenticated POST with a malformed body answered 422, which
# both leaks that the endpoint exists and reports the wrong problem: the caller
# is not authorised, and the shape of their body is none of their business yet.
# Handlers still resolve identity through `_client_id`, so this is defence in
# depth rather than a second source of truth.
router = APIRouter(tags=["chat"], dependencies=[Depends(current_user)])

# Input caps (defense-in-depth): reject oversized text / images before the LLM.
MAX_QUERY_CHARS = 8000
MAX_IMAGE_B64_CHARS = 12_000_000  # ~9 MB decoded


# ── request / response models ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    query: str = ""
    image_b64: str | None = None
    conversation_id: str | None = None  # None -> start a new conversation
    links: list[str] = []               # optional external URLs to attach to the message


class SourceLink(BaseModel):
    incident_id: str | None = None
    title: str | None = None
    source: str | None = None
    filename: str | None = None
    open_url: str | None = None         # in-app route to open the cited report
    score: float | None = None


class Artifact(BaseModel):
    language: str          # sql, bash, python, java, yaml, json, ... (drives highlighting)
    title: str = ""
    content: str


class ChatAnswer(BaseModel):
    answer: str
    incident_type: str
    confidence: int
    low_confidence: bool
    steps: list[dict]
    artifacts: list[Artifact]           # typed supporting artifacts (not SQL-only)
    supporting_sql: list[str]           # kept for backward compatibility
    matched_report_ids: list[str]
    retrieval: list[SourceLink]
    raw: str
    is_chat: bool = False               # True for greeting/smalltalk (no incident)
    needs_clarification: bool = False   # too vague / insufficient evidence to diagnose
    security_note: str | None = None    # set when prompt-injection was detected
    # Report sections: Problem Summary (answer) / Root Cause / Investigation /
    # Resolution Steps (steps) / Validation / Additional Notes.
    root_cause: str = ""
    investigation: str = ""
    validation: str = ""
    additional_notes: str = ""
    has_media: bool = False             # source report includes screenshots
    no_documented_resolution: bool = False
    ai_suggestion: str = ""             # shown marked as AI-suggested, not documented
    refused: bool = False               # out-of-scope / injection refusal
    # Irreversible operations found in the steps (see chatbot/hazard.py). The
    # UI outlines those steps and warns; `hazard_ungrounded` means no report
    # documents the procedure, so nobody has run it against this estate.
    hazards: list[str] = []
    has_hazard: bool = False
    hazard_ungrounded: bool = False


def _to_answer(parsed: dict) -> ChatAnswer:
    """Shape a pipeline dict into the API ChatAnswer."""
    return ChatAnswer(
        answer=parsed.get("incident_summary", ""),
        incident_type=parsed.get("incident_type", "Unknown"),
        confidence=parsed.get("confidence", 0),
        low_confidence=parsed.get("low_confidence", True),
        steps=parsed.get("recommended_resolution", []),
        artifacts=parsed.get("artifacts", []),
        supporting_sql=parsed.get("supporting_sql", []),
        matched_report_ids=parsed.get("matched_report_ids", []),
        retrieval=parsed.get("retrieval", []),
        raw=parsed.get("raw", ""),
        is_chat=parsed.get("is_chat", False),
        needs_clarification=parsed.get("needs_clarification", False),
        security_note=parsed.get("security_note"),
        root_cause=parsed.get("root_cause", ""),
        investigation=parsed.get("investigation", ""),
        validation=parsed.get("validation", ""),
        additional_notes=parsed.get("additional_notes", ""),
        has_media=parsed.get("has_media", False),
        no_documented_resolution=parsed.get("no_documented_resolution", False),
        ai_suggestion=parsed.get("ai_suggestion", ""),
        refused=parsed.get("refused", False),
        hazards=parsed.get("hazards", []),
        has_hazard=parsed.get("has_hazard", False),
        hazard_ungrounded=parsed.get("hazard_ungrounded", False),
    )


class ChatResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    answer: ChatAnswer


class Conversation(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float
    # Absent on the SQLite store, which has no such column — defaulted rather
    # than required so both backends satisfy this model.
    pinned: bool = False


class Message(BaseModel):
    id: str
    role: str
    text: str
    has_image: bool
    payload: dict | None = None
    feedback: int | None = None   # thumbs: 1 up, -1 down, None none
    created_at: float


# ── helpers ───────────────────────────────────────────────────────────────────


def _client_id(x_client_id: str | None, request: Request | None = None) -> str:
    """Resolve the caller's stable identifier.

    Kept as one function rather than converting 23 call sites to a FastAPI
    dependency: every handler already funnels identity through here, so this is
    the single place where "who is asking" is decided.

    With auth enabled the answer is the verified OIDC subject and the header is
    ignored — a client that keeps sending X-Client-Id cannot use it to act as
    someone else. With AUTH_DISABLED=1 the old header behaviour is preserved
    exactly, including this error message, which is what lets the existing
    tests run unchanged.
    """
    if not auth_disabled() and request is not None:
        authorization = request.headers.get("authorization")
        return current_user(request, authorization, x_client_id).id

    if not x_client_id or not x_client_id.strip():
        raise HTTPException(status_code=400, detail="X-Client-Id header is required")
    return x_client_id.strip()


def _store(request: Request):
    return request.app.state.chat_store


def _feedback_scores(store) -> dict[str, int]:
    """Net thumbs per report, for feedback-aware source selection.

    Tolerant by design: this is a ranking nicety, so a store that predates the
    method (or a transient read failure) degrades to "no signal" rather than
    failing the user's question.
    """
    getter = getattr(store, "report_feedback_scores", None)
    if getter is None:
        return {}
    try:
        return getter()
    except Exception:  # noqa: BLE001 — never fail a chat over a ranking hint
        log.warning("could not load report feedback scores", exc_info=True)
        return {}


def _title_from_query(query: str) -> str:
    q = query.strip().replace("\n", " ")
    return (q[:60] + "…") if len(q) > 60 else (q or "New conversation")


def _validate_and_service(body: ChatRequest, request: Request):
    """Shared guards for both chat endpoints: service ready + input limits."""
    service = request.app.state.chatbot
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.chatbot_error or "Chatbot is unavailable.",
        )
    if not body.query.strip() and not body.image_b64:
        raise HTTPException(status_code=400, detail="query or image_b64 is required")
    if len(body.query) > MAX_QUERY_CHARS:
        raise HTTPException(status_code=413, detail="Message is too long.")
    if body.image_b64 and len(body.image_b64) > MAX_IMAGE_B64_CHARS:
        raise HTTPException(status_code=413, detail="Attached image is too large.")
    return service


def _open_turn(body: ChatRequest, client_id: str, store) -> tuple[str, list[dict]]:
    """Resolve/create the conversation, persist the (redacted) user turn, and
    return (conversation_id, prior_history) for multi-turn context."""
    conversation_id = body.conversation_id
    if conversation_id:
        if not store.get_conversation(client_id, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = store.create_conversation(client_id, _title_from_query(body.query))
        conversation_id = conv["id"]

    # Prior turns BEFORE we add this one -> multi-turn memory for the pipeline.
    history = store.list_messages(client_id, conversation_id)

    # Redact secrets/PII before anything is persisted.
    safe_text = redact(body.query)
    user_payload = {"links": body.links} if body.links else None
    store.add_message(
        conversation_id,
        role="user",
        text=safe_text,
        has_image=bool(body.image_b64),
        payload=user_payload,
    )
    return conversation_id, history


# ── the pipeline (blocking) ───────────────────────────────────────────────────


@router.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> ChatResponse:
    client_id = _client_id(x_client_id, request)
    store = _store(request)
    service = _validate_and_service(body, request)

    conversation_id, history = _open_turn(body, client_id, store)
    corrections = store.relevant_corrections(body.query)

    # Run the pipeline (text-only, image+text, image-only) with prior context.
    # If the model backend is unreachable, surface a clear 503 instead of a
    # fabricated low-confidence answer (the "fast but wrong" failure mode).
    try:
        parsed = service.answer(body.query, body.image_b64, history=history,
                                corrections=corrections,
                                feedback_scores=_feedback_scores(store))
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"The local AI model is not reachable ({exc}). Is Ollama running?",
        )
    answer = _to_answer(parsed)

    assistant_msg = store.add_message(
        conversation_id,
        role="assistant",
        text=answer.answer,
        payload=answer.model_dump(),
    )
    return ChatResponse(
        conversation_id=conversation_id,
        user_message_id="",  # ids no longer needed by the client; kept for shape
        assistant_message_id=assistant_msg["id"],
        answer=answer,
    )


# ── the pipeline (streaming, SSE) ─────────────────────────────────────────────


@router.post("/api/chat/stream")
def chat_stream(
    body: ChatRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> StreamingResponse:
    client_id = _client_id(x_client_id, request)
    store = _store(request)
    service = _validate_and_service(body, request)

    conversation_id, history = _open_turn(body, client_id, store)
    corrections = store.relevant_corrections(body.query)
    feedback_scores = _feedback_scores(store)

    def event_stream():
        # Tell the client its conversation id up front (needed for a new chat).
        yield _sse({"type": "meta", "conversation_id": conversation_id})

        try:
            for ev in service.answer_stream(body.query, body.image_b64, history=history,
                                            corrections=corrections,
                                            feedback_scores=feedback_scores):
                if ev["type"] == "done":
                    answer = _to_answer(ev["answer"])
                    # Persist the completed assistant turn, then emit it.
                    msg = store.add_message(
                        conversation_id,
                        role="assistant",
                        text=answer.answer,
                        payload=answer.model_dump(),
                    )
                    yield _sse({
                        "type": "done",
                        "assistant_message_id": msg["id"],
                        "answer": answer.model_dump(),
                    })
                else:
                    yield _sse(ev)  # token / chat events pass through
        except LLMUnavailable as exc:
            # Loud, honest failure — not a fabricated answer.
            yield _sse({
                "type": "error",
                "detail": f"The local AI model is not reachable ({exc}). Is Ollama running?",
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    """Encode one Server-Sent Event line."""
    return f"data: {json.dumps(obj)}\n\n"


# ── feedback (thumbs) ─────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    value: int | None = None   # 1 up, -1 down, null to clear


@router.post("/api/messages/{message_id}/feedback")
def set_feedback(
    message_id: str,
    body: FeedbackRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    if body.value not in (1, -1, None):
        raise HTTPException(status_code=400, detail="value must be 1, -1, or null")
    ok = _store(request).set_feedback(_client_id(x_client_id, request), message_id, body.value)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"success": True}


class CorrectionRequest(BaseModel):
    question: str      # the incident question that got a wrong answer
    correction: str    # the correct guidance the human provides


@router.post("/api/corrections")
def add_correction(
    body: CorrectionRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    """Record a human correction so future similar questions use it.

    This is the loop that makes thumbs-down actionable: the correction is stored
    and injected into the prompt for later matching incidents (see
    store.relevant_corrections + service corrections handling)."""
    if not body.question.strip() or not body.correction.strip():
        raise HTTPException(status_code=400, detail="question and correction are required")
    saved = _store(request).add_correction(
        _client_id(x_client_id, request), body.question, body.correction
    )
    return {"success": True, "id": saved["id"]}


@router.get("/api/corrections")
def list_corrections(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    user: AuthContext = Depends(require_admin),
) -> dict:
    """Review stored corrections. Admin-only, for the same reason the summary
    is: corrections are global (any user's correction steers every user's
    answers), so reading them exposes other people's activity."""
    store = _store(request)
    getter = getattr(store, "list_corrections", None)
    if getter is None:
        raise HTTPException(status_code=501, detail="This store cannot list corrections.")
    return {"corrections": getter(limit)}


@router.delete("/api/corrections/{correction_id}")
def delete_correction(
    correction_id: str,
    request: Request,
    user: AuthContext = Depends(require_admin),
) -> dict:
    """Retract a correction so it stops being injected into future prompts."""
    store = _store(request)
    deleter = getattr(store, "delete_correction", None)
    if deleter is None:
        raise HTTPException(status_code=501, detail="This store cannot delete corrections.")
    if not deleter(correction_id):
        raise HTTPException(status_code=404, detail="Correction not found")
    return {"success": True}


@router.get("/api/feedback/summary")
def feedback_summary(
    request: Request,
    user: AuthContext = Depends(require_admin),
) -> dict:
    """Aggregate metrics for tuning — which answers land, which don't.

    Admin-only. It reports across *all* users, so an ordinary account reading it
    would learn about activity that is not theirs; it was unauthenticated
    before this phase, which a route test caught.
    """
    return _store(request).feedback_summary()


@router.get("/api/messages/{message_id}/html", response_class=HTMLResponse)
def message_html(
    message_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> HTMLResponse:
    """Render a stored answer as HTML, with the cited report's screenshots.

    The chat panel renders the structured answer, but a documented procedure
    often relies on screenshots that live in the source report rather than in
    the answer. This view embeds them inline so the procedure can be read (or
    exported) complete.
    """
    from app.chatbot.answer_html import render_answer_html

    client_id = _client_id(x_client_id, request)
    store = _store(request)

    answer = store.get_message_payload(client_id, message_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Message not found")

    # Pull images from the first cited report, when it is still on disk. The
    # citation may point at the markdown mirror, which carries no images, so
    # fall back to its JSON sibling — that is where the blocks (and screenshots)
    # actually live.
    report = None
    service = request.app.state.report_service
    for source in answer.get("retrieval") or []:
        filename = source.get("filename")
        if not filename:
            continue
        candidates = [filename]
        if filename.endswith(".md"):
            candidates.insert(0, filename[:-3] + ".json")
        for candidate in candidates:
            try:
                report = service.get_content(candidate)
                break
            except Exception:  # noqa: BLE001 — missing report just means no images
                continue
        if report:
            break

    return HTMLResponse(render_answer_html(answer, report))


class FollowupRequest(BaseModel):
    # The frontend already holds the question text in memory (it rendered it),
    # so it is supplied here rather than re-derived server-side by scanning the
    # conversation for "the previous user message" — that search is ambiguous
    # in a multi-turn thread and costs a round trip this endpoint doesn't need.
    # It is prompt input only, never trusted as identity: message_id is what
    # proves the caller owns this answer.
    question: str = ""


@router.post("/api/messages/{message_id}/followups")
def message_followups(
    message_id: str,
    body: FollowupRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    """Suggest 2-3 follow-up questions for a previously-answered message.

    On demand, not automatic: generating these costs a real LLM call (see
    chatbot/followups.py), so it runs only when a user asks for it rather than
    after every turn. 503 mirrors /api/chat's contract when the chatbot isn't
    up; empty results are a normal, silent outcome, not an error.
    """
    client_id = _client_id(x_client_id, request)
    answer = _store(request).get_message_payload(client_id, message_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Message not found")

    suggester = getattr(request.app.state, "followups", None)
    if suggester is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.chatbot_error or "Chatbot is unavailable.",
        )

    questions = suggester.suggest(body.question, answer)
    return {"questions": questions}


# ── chat-to-report ────────────────────────────────────────────────────────────


@router.post("/api/conversations/{conversation_id}/report")
def generate_report(
    conversation_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    """Turn a diagnosed conversation into a saved incident report.

    Builds an IncidentReport strictly from the conversation (symptom, diagnosis,
    steps, artifacts, cited reports — nothing invented), validates it against the
    schema, and persists it via the report generator's ReportService using its
    existing file-naming convention.
    """
    from app.chatbot.report_builder import (
        NoDiagnosisError,
        build_report_from_conversation,
    )
    from app.reports.service import DuplicateReportError

    client_id = _client_id(x_client_id, request)
    store = _store(request)
    if not store.get_conversation(client_id, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = store.list_messages(client_id, conversation_id)
    try:
        report, markdown = build_report_from_conversation(messages)
    except NoDiagnosisError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    report_service = request.app.state.report_service
    try:
        result = report_service.save(report, markdown)
    except DuplicateReportError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    # Return the saved filename + the report so the UI can open it in the viewer.
    return {"success": True, "report": report.model_dump(), **result}


# ── search ────────────────────────────────────────────────────────────────────


def _search(request: Request):
    """The ChatSearch built in the lifespan, or None on the SQLite backend."""
    return getattr(request.app.state, "chat_search", None)


@router.get("/api/search")
def search_chats(
    request: Request,
    q: str = Query(default="", max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    group: bool = Query(
        default=True,
        description="Collapse message hits to their conversations (sidebar view)",
    ),
    conversation_id: str | None = Query(default=None),
    x_client_id: str | None = Header(default=None),
) -> dict:
    """Hybrid search across the caller's own chat history.

    Keyword (tsvector/GIN) and semantic (pgvector) rankings fused with the same
    RRF the knowledge-base retrieval uses — see `app/shared/fusion.py`. Scoped
    to the caller: there is no cross-user search path.

    Returns an empty result rather than 501 when the store has no search
    backend, so the UI can show "no matches" instead of an error the user
    cannot act on.
    """
    client_id = _client_id(x_client_id, request)
    query = (q or "").strip()
    searcher = _search(request)

    if not query or searcher is None:
        return {"query": query, "results": [], "grouped": group,
                "available": searcher is not None}

    if group:
        results = searcher.search_conversations(client_id, query, limit=limit)
    else:
        results = [
            hit.as_dict()
            for hit in searcher.search(
                client_id, query, limit=limit, conversation_id=conversation_id
            )
        ]
    return {"query": query, "results": results, "grouped": group, "available": True}


# ── conversation CRUD ─────────────────────────────────────────────────────────


@router.get("/api/conversations", response_model=list[Conversation])
def list_conversations(
    request: Request, x_client_id: str | None = Header(default=None)
) -> list[Conversation]:
    return _store(request).list_conversations(_client_id(x_client_id, request))


class RenameRequest(BaseModel):
    title: str


class PinRequest(BaseModel):
    pinned: bool


@router.get("/api/conversations/{conversation_id}/messages", response_model=list[Message])
def list_messages(
    conversation_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> list[Message]:
    client_id = _client_id(x_client_id, request)
    store = _store(request)
    if not store.get_conversation(client_id, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return store.list_messages(client_id, conversation_id)


@router.patch("/api/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    body: RenameRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    ok = _store(request).rename_conversation(
        _client_id(x_client_id, request), conversation_id, body.title.strip() or "Untitled"
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@router.post("/api/conversations/{conversation_id}/pin")
def pin_conversation(
    conversation_id: str,
    body: PinRequest,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    """Pin a conversation to the top of the sidebar.

    Returns 501 rather than a silent success on a store without pinning (the
    SQLite fallback), so the UI can hide the control instead of offering one
    that does nothing.
    """
    store = _store(request)
    if not hasattr(store, "set_pinned"):
        raise HTTPException(
            status_code=501, detail="Pinning requires the Postgres chat store"
        )
    ok = store.set_pinned(
        _client_id(x_client_id, request), conversation_id, body.pinned
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "pinned": body.pinned}


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    ok = _store(request).delete_conversation(_client_id(x_client_id, request), conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}
