# NTT Incident Platform

Unified application merging the **incident-report-generator** (React/TS) and the
**Chatbot** (Python RAG over incident reports) into one product: a single React
frontend with two modules (Report Generator, Chatbot) backed by one FastAPI
service.

## Why this shape

The two original projects already share a data contract — the
`{ metadata, blocks[] }` report JSON that the generator *writes* and the chatbot
*ingests*. That shared schema (codified in `backend/app/shared/schema.py` ↔
`frontend/src/types.ts`) is the integration seam. The frontend stays React; the
Python chatbot becomes a headless FastAPI service; the old Express `server.ts`
is replaced by `backend/app/routers/reports.py`.

Architecture: **modular monolith** — one backend process, clean module
boundaries (`chatbot/`, `reports/`, `shared/`), no microservice overhead.

> **Data layer.** On the `platform-hardening` branch this app runs on Postgres
> (identity, chat, search), MinIO (report blobs, versioned) and Keycloak
> (OIDC auth), with hybrid keyword + semantic search over chat history.
> See **[docs/PLATFORM_HARDENING.md](docs/PLATFORM_HARDENING.md)** for the
> architecture, the migration commands, and what the real data exposed.
> `main` keeps the earlier SQLite + filesystem + no-auth version.

## Layout

```
ntt-incident-platform/
├── frontend/                 # React 18 + Vite + Tailwind v4
│   └── src/auth/             # OIDC PKCE flow, auth context, login screen
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint (replaces server.ts)
│   │   ├── routers/          # HTTP layer: reports.py, chat.py
│   │   ├── reports/          # report CRUD: filesystem + object-storage services
│   │   ├── chatbot/          # RAG/LLM pipeline
│   │   ├── auth/             # OIDC validation, role guards
│   │   ├── db/               # models, chat repository, hybrid search
│   │   └── shared/           # schema.py (contract), llm/, storage/, fusion.py
│   ├── alembic/              # schema migrations
│   ├── tests/
│   └── requirements.txt
├── reports/                  # shared report data (source for the MinIO migration)
├── scripts/                  # migrate_to_postgres.py, migrate_reports_to_minio.py
└── infra/                    # Dockerfile.backend, docker-compose.yml, keycloak/
```

## Run the full app locally

Prereq for real chatbot answers: `ollama serve` running with
`ollama pull llama3:8b && ollama pull qwen2.5vl:3b`.

**Option A — Docker, one command (recommended).** Builds the frontend and backend
into one image; FastAPI serves the SPA. Talks to your host Ollama by default.

```bash
docker compose -f infra/docker-compose.yml up --build   # http://localhost:8000
```

See [infra/README.md](infra/README.md) for the Ollama-in-a-container variant and
config knobs.

The reports in `reports/` are tracked in git, so a fresh clone has them. On the
MinIO backend the bucket starts empty, so the backend **seeds it from
`reports/` on first boot** — otherwise the chatbot (which indexes the directory
directly) would answer from reports the UI could not list. Seeding only happens
when the bucket is empty, so a restart never resurrects a report deleted through
the UI. Disable it with `SEED_REPORTS=0`; to re-sync an already-populated bucket
by hand, use `python scripts/migrate_reports_to_minio.py`.

**Option B — no Docker, one server (prod-like).** FastAPI serves the built SPA:

```bash
cd frontend && npm install && npm run build   # produces frontend/dist
cd ../backend && ./dev.sh                      # http://localhost:8000  (whole app)
```

**Option C — no Docker, two servers (hot-reload dev).** Vite proxies /api:

```bash
cd backend && ./dev.sh                          # backend on :8000
cd frontend && npm install && npx vite          # UI on :5173, proxies /api -> :8000
```

Backend tests: `cd backend && ./.venv/bin/pytest` (18 tests, no Ollama needed —
the chatbot pipeline is exercised with fakes).

## API (report endpoints, ported 1:1 from server.ts)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/reports` | create or update; `409` on duplicate incident_id |
| GET | `/api/reports` | list, newest first |
| GET | `/api/reports/content/{filename}` | parsed JSON; `404` if missing |
| GET | `/api/reports/download/{filename}` | download raw file |
| GET | `/api/download?filename=` | download (query variant) |
| GET | `/api/html?filename=` | standalone HTML export |
| DELETE | `/api/delete/{filename}` | delete json+md pair |
| DELETE | `/api/delete?incident_id=` | delete latest for an incident |

## Migration status

- [x] **Phase 0** — unified repo skeleton
- [x] **Phase 1** — FastAPI backend; reports router (server.ts port); shared schema
- [x] **Phase 2** — chatbot ported into `app/chatbot/`, Streamlit removed;
      `/api/chat` live; swappable Ollama/Gemini LLM providers
- [x] **Phase 3** — frontend moved into `frontend/`; chatbot module (chat UI) +
      report module under one sidebar-navigated React shell
- [x] **Phase 4** — `docker compose up` runs it all locally (see `infra/`)
- [ ] **Phase 5** — hardening (auth, SharePoint adapter) — deferred

### Chatbot module (Phase 2)

`POST /api/chat` — body `{ "query": "...", "image_b64": null }` — runs
understand → hybrid retrieval over the shared reports KB → expert-resolution LLM
call → parsed structured response. Returns `503` if the chatbot didn't
initialise (missing model/Ollama); `/api/health` reports `chatbot_ready`.

- LLM provider is swappable via `CHATBOT_PROVIDER=ollama|gemini` (default
  `ollama`, self-hosted). See `app/shared/llm/`.
- The embedding model + KB index are built once in the app lifespan (where the
  old Streamlit `@st.cache_resource` singletons moved to).
- Set `DISABLE_CHATBOT=1` to boot the reports-only surface without loading the
  embedding model (used by the reports tests).

Run Ollama for real answers: `ollama pull llama3:8b && ollama pull qwen2.5vl:3b`.

## Notes for Phase 2

- `backend/app/shared/llm/provider.py` defines the swappable `LLMProvider`
  interface. Implement `OllamaProvider` (wrap the chatbot's `ask_ollama` /
  `run_vlm`) and `GeminiProvider` (move the generator's browser-side Gemini
  calls server-side), then wire `get_provider`.
- The chatbot currently imports `streamlit` inside `llm.py`, `ingestion.py`, and
  `resolution.py` — not just `ui.py`. Removing that is the main work: replace
  `@st.cache_resource` singletons (embedding model, KB index) with objects built
  in `main.py`'s lifespan, and `st.session_state` with request-scoped data.
```
