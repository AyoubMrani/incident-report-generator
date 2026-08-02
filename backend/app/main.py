"""
main.py — FastAPI application entrypoint for the unified NTT incident platform.

Replaces the Express server.ts. Responsibilities:
  - build long-lived services in the lifespan (ReportService now; the chatbot
    embedding model / KB index will join here in Phase 2 — this is where the
    Streamlit @st.cache_resource singletons move to)
  - mount the API routers
  - allow the Vite dev server (localhost:5173) to call the API during dev

In production the built frontend (frontend/dist) is served as static files by
this same app, so there is one process and one origin.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.reports.service import ReportService
from app.shared.logging import configure_logging, get_logger
from app.routers import chat, reports

# Repo layout: backend/app/main.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", REPO_ROOT / "reports"))
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
# SQLite file for persistent chat conversations (survives restarts).
CHAT_DB = Path(os.environ.get("CHAT_DB", REPO_ROOT / "data" / "chat.db"))

# Which LLM provider the chatbot uses. Swappable per the architecture decision;
# defaults to self-hosted Ollama for the local setup.
CHATBOT_PROVIDER = os.environ.get("CHATBOT_PROVIDER", "ollama")

# Building the chatbot KB loads sentence-transformers and embeds every report,
# which is slow and needs the model available. Skip it in tests / when the
# reports-only surface is all that's needed, via DISABLE_CHATBOT=1.
DISABLE_CHATBOT = os.environ.get("DISABLE_CHATBOT") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app.startup")

    # Startup: construct services once and stash on app.state.
    app.state.report_service = ReportService(REPORTS_DIR)

    # Persistent chat store (SQLite). Independent of the chatbot pipeline, so
    # conversation history stays browsable even if the LLM/KB fails to load.
    from app.chatbot.store import ChatStore

    app.state.chat_store = ChatStore(CHAT_DB)

    # Build the chatbot once (embedding model + KB index live for the process
    # lifetime — this is where the old @st.cache_resource singletons moved to).
    # Non-fatal: if deps/model/Ollama aren't available, the app still boots and
    # /api/chat returns 503 with the reason, so the reports module keeps working.
    app.state.chatbot = None
    app.state.chatbot_error = None
    if DISABLE_CHATBOT:
        app.state.chatbot_error = "Chatbot disabled via DISABLE_CHATBOT=1."
        log.info("chatbot disabled via DISABLE_CHATBOT=1")
    else:
        started = time.perf_counter()
        try:
            from app.chatbot.service import ChatbotService
            from app.shared.llm.provider import get_provider

            provider = get_provider(CHATBOT_PROVIDER)
            app.state.chatbot = ChatbotService.build(REPORTS_DIR, provider)
            kb = app.state.chatbot.kb
            log.info(
                "knowledge base indexed: %d files, %d chunks in %.1fs",
                kb.n_files, len(kb.documents), time.perf_counter() - started,
                extra={"event": "kb_indexed", "files": kb.n_files,
                       "chunks": len(kb.documents),
                       "duration_ms": round((time.perf_counter() - started) * 1000)},
            )
            for warning in kb.warnings:
                log.warning("indexing warning: %s", warning)
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash boot
            app.state.chatbot_error = f"{type(exc).__name__}: {exc}"
            # exc_info: without the traceback this failure is near-undiagnosable
            # in production — /api/health only carries the one-line summary.
            log.error("chatbot failed to start: %s", exc, exc_info=True,
                      extra={"event": "chatbot_start_failed"})

    yield
    # Shutdown: nothing to release yet.
    log.info("shutting down", extra={"event": "shutdown"})


app = FastAPI(title="NTT Incident Platform", lifespan=lifespan)

# Dev-only CORS: the Vite dev server runs on a different origin than the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(chat.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "chatbot_ready": app.state.chatbot is not None,
        "chatbot_error": app.state.chatbot_error,
    }


# Serve the built SPA in production (mirrors the express.static + SPA fallback
# in server.ts). Guarded so the app still boots in dev before a build exists.
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # Any non-API path returns index.html so client-side routing works.
        return FileResponse(FRONTEND_DIST / "index.html")
