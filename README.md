<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 54" src="https://github.com/user-attachments/assets/af9d044a-9ded-4fcc-9c8f-6ef4549825e6" /># NTT Incident Platform

Unified application merging the **incident-report-generator** (React/TS) and the
**Chatbot** (Python RAG over incident reports) into one product: a single React
frontend with two modules (Report Generator, Chatbot) backed by one FastAPI
service.

<img width="1379" height="901" alt="Pictureq1" src="https://github.com/user-attachments/assets/f41a23dc-e8cf-44f5-87a0-b31e0f2c9cda" />

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

**Where reports live.** On the MinIO backend, object storage is the single
source of truth: the report listing, report downloads, and the chatbot's
retrieval index all read the bucket. `reports/` is the *seed corpus* only —
tracked in git so a fresh clone has something to start from, and read at
startup to fill gaps in the bucket. Nothing reads it at request time.

Seeding is per file: any corpus file whose key is missing is uploaded, so a
bucket that already holds a user's own report still receives the corpus. Keys
the catalog marks deleted — or that carry a `_deleted/` tombstone, which is how
the no-database configuration records the same intent — are skipped, so a
restart never resurrects a report removed through the UI. Disable seeding with
`SEED_REPORTS=0`; to re-sync by hand, use
`python scripts/migrate_reports_to_minio.py`.

`GET /api/health` reports `reports_visible` and `chatbot_source` (`storage` or
`directory`). They exist because the listing and the chatbot once read
different sources — the UI showed an empty list while the chatbot answered from
reports it alone could see, and every other health field looked fine.

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

## Evidence

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 02 09" src="https://github.com/user-attachments/assets/f4879064-5adf-431d-b90a-3060d8268526" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 22 59 52" src="https://github.com/user-attachments/assets/c18c5a85-fb25-45d3-967c-b6e9f054d520" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 22 59 34" src="https://github.com/user-attachments/assets/04cae78a-7bcc-4da1-a58f-1a3c0a6d5924" />

<img width="1624" height="1061" alt="image (1)" src="https://github.com/user-attachments/assets/baf76526-5fad-4c00-9885-840eb5d231da" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 22 59 39" src="https://github.com/user-attachments/assets/717644cd-756d-4bf9-b58f-22004225c2da" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 06" src="https://github.com/user-attachments/assets/41371075-0105-4ca2-81ea-30ac6c7782a3" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 12" src="https://github.com/user-attachments/assets/4f61fdc3-e7cb-4403-83b7-7c2da4e0d39f" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 31" src="https://github.com/user-attachments/assets/ee367262-5039-4650-8ec4-d66348b768d5" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 54" src="https://github.com/user-attachments/assets/1dd3c343-d19b-4ee2-a76f-b571060b46d4" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 01 29" src="https://github.com/user-attachments/assets/39aaf469-3c2b-45f1-8629-f266338f1b99" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 01 37" src="https://github.com/user-attachments/assets/6c516dd9-ca70-453c-84ba-3e62fec57577" />

<img width="1624" height="1061" alt="Screenshot 2026-08-07 at 23 00 58" src="https://github.com/user-attachments/assets/b9efc8af-3dc9-4655-9f99-abb1b1a3965e" />





















```



