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

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth.dependencies import AuthContext
from app.auth.dependencies import current_user as _current_user
from app.reports.service import ReportService
from app.shared.logging import configure_logging, get_logger
from app.routers import chat, profile, reports

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

# Upload any corpus file the report bucket is missing at startup, so a fresh
# clone lists the same reports the chatbot indexes. On by default: a bucket
# without the corpus on a first run is the bug, not a state anyone chooses. Set
# SEED_REPORTS=0 where the bucket is authoritative and must never be written
# from local files.
SEED_REPORTS = os.environ.get("SEED_REPORTS", "1").strip().lower() not in (
    "0", "false", "no",
)

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

    # ── authentication ────────────────────────────────────────────────────────
    # Checked first and allowed to raise: refusing to boot is the correct
    # response to "auth is off in production", and it must happen before any
    # request can be served.
    from app.auth.dependencies import assert_auth_config_sane, auth_disabled
    from app.auth.oidc import OIDCValidator

    assert_auth_config_sane()

    if auth_disabled():
        app.state.oidc = None
        log.warning(
            "AUTH_DISABLED=1 — identity comes from the X-Client-Id header and "
            "is NOT verified. Local development only.",
            extra={"event": "auth_disabled"},
        )
    else:
        app.state.oidc = OIDCValidator()
        # Non-fatal: Keycloak may still be starting. Tokens fail closed (401)
        # until it answers, which is the safe direction to degrade.
        if app.state.oidc.ready():
            log.info("auth: OIDC via %s", app.state.oidc.issuer,
                     extra={"event": "auth_ready"})
        else:
            log.error(
                "OIDC issuer %s is not reachable; requests will fail with 401 "
                "until it is", app.state.oidc.issuer,
                extra={"event": "auth_issuer_unreachable"},
            )

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
    app.state.report_storage = None
    if STORAGE_BACKEND in ("minio", "s3"):
        try:
            from app.reports.storage_service import StorageReportService
            from app.shared.storage.factory import get_storage

            storage = get_storage(STORAGE_BACKEND)
            if not storage.health():
                raise RuntimeError(f"storage backend {STORAGE_BACKEND} unreachable")
            app.state.report_service = StorageReportService(storage, app.state.db)
            app.state.report_storage = storage
            log.info("report storage: %s", STORAGE_BACKEND,
                     extra={"event": "storage_ready", "backend": STORAGE_BACKEND})

            # A fresh clone has the reports on disk (they are tracked in git)
            # but not in the bucket, so the chatbot — which indexes REPORTS_DIR
            # directly — answered from reports the UI could not list. Seed the
            # bucket from the same directory so both surfaces start in
            # agreement. Uploads per file, so a bucket already holding a user's
            # own report still receives the corpus; keys the catalog marks
            # deleted are skipped, so a restart never resurrects them.
            if SEED_REPORTS:
                from app.reports.seed import seed_reports

                try:
                    seed_reports(
                        REPORTS_DIR, app.state.report_service, storage, log
                    )
                except Exception as exc:  # noqa: BLE001 — degrade, don't crash
                    log.error(
                        "report seeding failed (%s); the bucket may be empty. "
                        "Run scripts/migrate_reports_to_minio.py to populate it.",
                        exc, exc_info=True, extra={"event": "seed_failed"},
                    )
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
    app.state.chat_search = None
    if CHAT_BACKEND == "postgres" and app.state.db is not None:
        from app.db.chat_repository import ChatRepository
        from app.db.search import ChatSearch

        app.state.chat_store = ChatRepository(app.state.db)
        # Built without an embedder for now; the chatbot's model is attached
        # below once it has loaded, so search never loads a second copy of it.
        # Until then search runs keyword-only, which is the honest degradation.
        app.state.chat_search = ChatSearch(app.state.db)
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
    app.state.followups = None
    if DISABLE_CHATBOT:
        app.state.chatbot_error = "Chatbot disabled via DISABLE_CHATBOT=1."
        log.info("chatbot disabled via DISABLE_CHATBOT=1")
    else:
        started = time.perf_counter()
        try:
            from app.chatbot.service import ChatbotService
            from app.shared.llm.provider import get_provider

            provider = get_provider(CHATBOT_PROVIDER)

            # Index the same corpus the report listing serves. When reports
            # live in object storage the chatbot reads it directly, so a report
            # saved through the UI is answerable after a refresh instead of
            # waiting for someone to re-index a local directory that never
            # received it. The directory remains the source only when the
            # filesystem backend is in use.
            report_storage = getattr(app.state, "report_storage", None)
            if STORAGE_BACKEND in ("minio", "s3") and report_storage is not None:
                app.state.chatbot = ChatbotService.build_from_storage(
                    report_storage, provider
                )
                # Resolution re-reads whole documents by the `path` in each
                # chunk, which is now an object key — teach it to fetch through
                # storage, or every full-document read would silently return
                # nothing and answers would fall back to bare chunks.
                from app.chatbot.resolution import set_document_reader

                def _read_object(key: str) -> str:
                    try:
                        return report_storage.get(key).decode("utf-8")
                    except Exception:  # noqa: BLE001 — caller falls back
                        return ""

                set_document_reader(_read_object)
            else:
                app.state.chatbot = ChatbotService.build(REPORTS_DIR, provider)
            kb = app.state.chatbot.kb

            # Same provider, same warm model — follow-up suggestion is a
            # separate, much smaller prompt, not a separate model or process.
            from app.chatbot.followups import FollowupSuggester

            app.state.followups = FollowupSuggester(provider)
            log.info(
                "knowledge base indexed: %d files, %d chunks in %.1fs",
                kb.n_files, len(kb.documents), time.perf_counter() - started,
                extra={"event": "kb_indexed", "files": kb.n_files,
                       "chunks": len(kb.documents),
                       "duration_ms": round((time.perf_counter() - started) * 1000)},
            )
            for warning in kb.warnings:
                log.warning("indexing warning: %s", warning)

            # Share the embedding model with chat search rather than loading a
            # second copy: it is ~90 MB resident and the machine also has to
            # hold Ollama's weights.
            if app.state.chat_search is not None:
                app.state.chat_search.embedder = kb.embed_model
                log.info("chat search: hybrid (keyword + semantic)",
                         extra={"event": "search_ready", "mode": "hybrid"})
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

# CORS.
#
# In production this app serves its own SPA from the same origin, so no
# cross-origin access is needed at all and the default list is empty. The Vite
# dev server (a different origin) is added only when APP_ENV is a development
# one — a hardcoded localhost allowance would otherwise ship to every
# deployment, and `allow_credentials` with a permissive origin list is the
# classic way to make an API readable by any page a user visits.
#
# CORS_ORIGINS (comma-separated) covers the real deployment case where the SPA
# is hosted separately.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()

_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if not _cors_origins and _APP_ENV in ("development", "dev", "local", "test"):
    _cors_origins = _DEV_ORIGINS

if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        # Narrowed from "*": these are the methods the API actually exposes.
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Client-Id"],
    )

app.include_router(reports.router)
app.include_router(chat.router)
app.include_router(profile.router)


@app.get("/api/health")
def health() -> dict:
    """Liveness plus the two dependencies that degrade independently.

    `database_ready` is probed per call rather than cached from boot: Postgres
    can go away while the process stays up, and a health check that reports its
    startup state would keep saying "ok" through the outage.
    """
    db = getattr(app.state, "db", None)

    # Reported because "the chatbot answers but the UI lists nothing" is the
    # one failure that looks healthy from every other field: the chatbot reads
    # REPORTS_DIR while the listing reads storage, so only a count of what the
    # *listing* can see distinguishes a seeded deployment from an empty one.
    service = getattr(app.state, "report_service", None)
    try:
        reports_visible = len(service.list_reports()) if service is not None else None
    except Exception:  # noqa: BLE001 — health must not fail on a degraded backend
        reports_visible = None

    return {
        "status": "ok",
        "chatbot_ready": app.state.chatbot is not None,
        "chatbot_error": app.state.chatbot_error,
        "chat_backend": getattr(app.state, "chat_backend", "unknown"),
        "storage_backend": getattr(app.state, "storage_backend", "unknown"),
        "reports_visible": reports_visible,
        # Where retrieval reads from. Reported because the listing and the
        # chatbot once read different sources: the UI showed an empty list
        # while the chatbot answered from reports it alone could see, and every
        # other health field looked fine throughout.
        "chatbot_source": (
            "storage"
            if getattr(getattr(app.state, "chatbot", None), "storage", None) is not None
            else ("directory" if getattr(app.state, "chatbot", None) else None)
        ),
        "database_ready": db.ping() if db is not None else None,
        "auth_enabled": getattr(app.state, "oidc", None) is not None,
    }


@app.get("/api/auth/config")
def auth_config() -> dict:
    """What the browser needs to start a login.

    Public by design — these are the values baked into any OIDC client — and it
    keeps the frontend from hardcoding a realm URL that differs per environment.
    """
    from app.auth.dependencies import auth_disabled

    oidc = getattr(app.state, "oidc", None)
    if oidc is None or auth_disabled():
        return {"enabled": False}
    return {
        "enabled": True,
        # The browser must use the externally reachable issuer, not the
        # container-internal one the backend validates against.
        "issuer": oidc.public_issuer or oidc.issuer,
        "client_id": oidc.audience,
    }


@app.get("/api/me")
def me(user: "AuthContext" = Depends(_current_user)) -> dict:
    """The signed-in user and what they may do.

    The frontend drives role-aware UI from this rather than decoding the token
    itself, so permission rules live in one place — the backend.
    """
    # Stored profile overrides the token's claims: a display name or avatar the
    # user set here is theirs to change, and Keycloak does not know about it.
    display_name, avatar_url = user.display_name, ""
    db = getattr(app.state, "db", None)
    if db is not None:
        try:
            from sqlalchemy import select

            from app.db.models import User as UserRow

            with db.session() as s:
                row = s.execute(
                    select(UserRow.display_name, UserRow.avatar_url).where(
                        UserRow.subject == user.id
                    )
                ).one_or_none()
            if row:
                display_name = row.display_name or display_name
                avatar_url = row.avatar_url or ""
        except Exception:
            # Identity still works without a profile; this is decoration.
            pass

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "roles": list(user.roles),
        "authenticated": user.authenticated,
        "is_admin": user.is_admin,
        "can_write": user.can_write,
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
