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

# Which chat store to build: "postgres" (the platform default) or "sqlite".
# Kept switchable so the migration is reversible without a code change, and so
# the test suite and a bare `uvicorn` run work with nothing else running.
CHAT_BACKEND = os.environ.get("CHAT_BACKEND", "postgres").strip().lower()

# Where report blobs live: "minio" or "filesystem". Defaults to filesystem so
# a checkout with nothing running still serves reports from reports/.
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "filesystem").strip().lower()

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

    # ── database ──────────────────────────────────────────────────────────────
    # Built first and shared: the chat store and the report catalog are two
    # users of one connection pool, not two pools.
    app.state.db = None
    if CHAT_BACKEND == "postgres" or STORAGE_BACKEND in ("minio", "s3"):
        from app.db.session import Database

        database = Database()
        if database.ping():
            app.state.db = database
        else:
            database.dispose()
            log.error(
                "postgres unreachable at startup; chat falls back to SQLite and "
                "report listing falls back to scanning storage",
                extra={"event": "database_unavailable"},
            )

    # ── report storage ────────────────────────────────────────────────────────
    # Blobs in object storage with a Postgres catalog, or the original
    # filesystem service. Both expose the same methods to the router.
    app.state.storage_backend = STORAGE_BACKEND
    if STORAGE_BACKEND in ("minio", "s3"):
        try:
            from app.reports.storage_service import StorageReportService
            from app.shared.storage.factory import get_storage

            storage = get_storage(STORAGE_BACKEND)
            if not storage.health():
                raise RuntimeError(f"storage backend {STORAGE_BACKEND} unreachable")
            app.state.report_service = StorageReportService(storage, app.state.db)
            log.info("report storage: %s", STORAGE_BACKEND,
                     extra={"event": "storage_ready", "backend": STORAGE_BACKEND})
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash boot
            app.state.storage_backend = "filesystem-fallback"
            app.state.report_service = ReportService(REPORTS_DIR)
            log.error(
                "object storage unavailable (%s); serving reports from %s. New "
                "reports will NOT be written to the bucket.", exc, REPORTS_DIR,
                exc_info=True, extra={"event": "storage_fallback"},
            )
    else:
        app.state.report_service = ReportService(REPORTS_DIR)
        log.info("report storage: filesystem (%s)", REPORTS_DIR,
                 extra={"event": "storage_ready", "backend": "filesystem"})

    # ── chat store ────────────────────────────────────────────────────────────
    # Independent of the chatbot pipeline, so conversation history stays
    # browsable even if the LLM/KB fails to load.
    #
    # Postgres is the default. If it cannot be reached the app falls back to the
    # SQLite file rather than refusing to start: the same "degrade, don't crash"
    # rule the chatbot follows below. The fallback is logged at ERROR because
    # running on it unknowingly means new chats land somewhere the rest of the
    # platform will not look for them.
    app.state.chat_backend = CHAT_BACKEND
    if CHAT_BACKEND == "postgres" and app.state.db is not None:
        from app.db.chat_repository import ChatRepository

        app.state.chat_store = ChatRepository(app.state.db)
        log.info("chat store: postgres",
                 extra={"event": "chat_store_ready", "backend": "postgres"})
    else:
        from app.chatbot.store import ChatStore

        if CHAT_BACKEND == "postgres":
            app.state.chat_backend = "sqlite-fallback"
            log.error(
                "postgres unreachable; falling back to SQLite at %s. New chats "
                "will NOT be visible to the platform database.", CHAT_DB,
                extra={"event": "chat_store_fallback"},
            )
        else:
            log.info("chat store: sqlite (%s)", CHAT_DB,
                     extra={"event": "chat_store_ready", "backend": "sqlite"})
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

    # Shutdown: return pooled connections. Without this, a reload loop leaks a
    # pool per generation and Postgres eventually refuses new clients.
    if app.state.db is not None:
        app.state.db.dispose()
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
    """Liveness plus the two dependencies that degrade independently.

    `database_ready` is probed per call rather than cached from boot: Postgres
    can go away while the process stays up, and a health check that reports its
    startup state would keep saying "ok" through the outage.
    """
    db = getattr(app.state, "db", None)
    return {
        "status": "ok",
        "chatbot_ready": app.state.chatbot is not None,
        "chatbot_error": app.state.chatbot_error,
        "chat_backend": getattr(app.state, "chat_backend", "unknown"),
        "storage_backend": getattr(app.state, "storage_backend", "unknown"),
        "database_ready": db.ping() if db is not None else None,
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
