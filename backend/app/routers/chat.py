"""
routers/chat.py — HTTP surface for the chatbot module.

Two concerns:
  1. The chat pipeline (POST /api/chat) — delegates to the ChatbotService.
  2. Persistent conversations — CRUD over the SQLite ChatStore so history
     survives restarts and syncs across a client's tabs.

Identity is the `X-Client-Id` header (a UUID the browser generates and keeps in
localStorage). Auth-free for now; when real accounts land, this header becomes
the authenticated user id and the store queries are unchanged.

Returns 503 for the pipeline when the chatbot didn't initialise; conversation
CRUD still works (it only needs the store), so history is browsable even if
Ollama is down.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.chatbot.security import redact
from app.shared.llm.provider import LLMUnavailable

router = APIRouter(tags=["chat"])

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


class ChatAnswer(BaseModel):
    answer: str
    incident_type: str
    confidence: int
    low_confidence: bool
    steps: list[dict]
    supporting_sql: list[str]
    matched_report_ids: list[str]
    retrieval: list[SourceLink]
    raw: str
    is_chat: bool = False               # True for greeting/smalltalk (no incident)
    security_note: str | None = None    # set when prompt-injection was detected


def _to_answer(parsed: dict) -> ChatAnswer:
    """Shape a pipeline dict into the API ChatAnswer."""
    return ChatAnswer(
        answer=parsed.get("incident_summary", ""),
        incident_type=parsed.get("incident_type", "Unknown"),
        confidence=parsed.get("confidence", 0),
        low_confidence=parsed.get("low_confidence", True),
        steps=parsed.get("recommended_resolution", []),
        supporting_sql=parsed.get("supporting_sql", []),
        matched_report_ids=parsed.get("matched_report_ids", []),
        retrieval=parsed.get("retrieval", []),
        raw=parsed.get("raw", ""),
        is_chat=parsed.get("is_chat", False),
        security_note=parsed.get("security_note"),
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


class Message(BaseModel):
    id: str
    role: str
    text: str
    has_image: bool
    payload: dict | None = None
    created_at: float


# ── helpers ───────────────────────────────────────────────────────────────────


def _client_id(x_client_id: str | None) -> str:
    if not x_client_id or not x_client_id.strip():
        raise HTTPException(status_code=400, detail="X-Client-Id header is required")
    return x_client_id.strip()


def _store(request: Request):
    return request.app.state.chat_store


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
    client_id = _client_id(x_client_id)
    store = _store(request)
    service = _validate_and_service(body, request)

    conversation_id, history = _open_turn(body, client_id, store)

    # Run the pipeline (text-only, image+text, image-only) with prior context.
    # If the model backend is unreachable, surface a clear 503 instead of a
    # fabricated low-confidence answer (the "fast but wrong" failure mode).
    try:
        parsed = service.answer(body.query, body.image_b64, history=history)
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
    client_id = _client_id(x_client_id)
    store = _store(request)
    service = _validate_and_service(body, request)

    conversation_id, history = _open_turn(body, client_id, store)

    def event_stream():
        # Tell the client its conversation id up front (needed for a new chat).
        yield _sse({"type": "meta", "conversation_id": conversation_id})

        try:
            for ev in service.answer_stream(body.query, body.image_b64, history=history):
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


# ── conversation CRUD ─────────────────────────────────────────────────────────


@router.get("/api/conversations", response_model=list[Conversation])
def list_conversations(
    request: Request, x_client_id: str | None = Header(default=None)
) -> list[Conversation]:
    return _store(request).list_conversations(_client_id(x_client_id))


class RenameRequest(BaseModel):
    title: str


@router.get("/api/conversations/{conversation_id}/messages", response_model=list[Message])
def list_messages(
    conversation_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> list[Message]:
    client_id = _client_id(x_client_id)
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
        _client_id(x_client_id), conversation_id, body.title.strip() or "Untitled"
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> dict:
    ok = _store(request).delete_conversation(_client_id(x_client_id), conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}
