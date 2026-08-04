# Platform Hardening — Plan

Branch: `platform-hardening` (off `main` @ `4dada6f`).
`main` holds the presented version and is not touched by this work.

**Deployment stance:** local only. Everything runs via
`docker compose -f infra/docker-compose.yml up`. No cloud, no public hosting.
Team members run the stack on their own machine. This version is not delivered.

## Why this work exists

The AI layer (hybrid retrieval, grounding gates, security, evaluation harness)
is solid and measured. What makes the project read as *small* is the layer
underneath it:

| Concern | Today | Problem |
|---|---|---|
| Identity | `X-Client-Id`, a UUID the browser invents | Not authentication. Anyone can send any id. |
| Reports | Loose files in a bind-mounted `reports/` dir | No versioning, no metadata query, no access control. |
| Chat | One SQLite file | Single-writer, no users, no search. |
| Search over chats | None | History is write-only past ~20 conversations. |

All five improvement points are the same fix: **give the demo a real data
layer**. That is the gap, and closing it is what turns a good model pipeline
into a system.

## Architecture decisions

Three new services. Deliberately three, not seven — each one has to earn its
container.

```
                      ┌──────────────┐
   browser ──OIDC──►  │   Keycloak   │  identity, roles, JWT issuance
                      └──────┬───────┘
                             │ validate JWT (JWKS)
                      ┌──────▼───────┐
                      │   FastAPI    │  app/auth, app/chatbot, app/reports
                      └──┬────────┬──┘
                 SQL     │        │     S3 API
              ┌──────────▼──┐  ┌──▼──────────┐
              │  Postgres   │  │   MinIO     │
              │  + pgvector │  │  versioned  │
              └─────────────┘  └─────────────┘
              users, convos,    report blobs:
              messages, FTS,    json / md / html
              report catalog    / attachments
```

### 1. Postgres replaces SQLite — the keystone

Chosen because it collapses three of the five points into one migration:

- **Point 1 (auth):** real `users` table, FK from `conversations.user_id`.
  `store.py:8` already documents this swap as the intended path.
- **Point 3 (chat storage):** durable, concurrent, multi-user.
- **Point 4 (search):** `tsvector` + GIN index gives ranked full-text search
  natively. `pgvector` gives semantic search over message embeddings.

No Elasticsearch. At this data volume it would be a second copy of the data,
a JVM, and 1–2 GB of RAM to do what one GIN index already does.

### 2. MinIO as blob source of truth, Postgres as catalog

The standard object-store pattern: **blobs in the bucket, metadata in the
database.**

- MinIO holds `reports/{incident_id}/{version}/report.json|report.md|export.html`
  plus attachments, with bucket versioning on.
- Postgres `reports` table holds incident_id, title, severity, dates, author,
  status, and the MinIO object key.

Listing and filtering become a SQL query instead of a directory scan and a
JSON parse per file. `backend/app/reports/service.py` was already written
framework-agnostic with a storage seam (its docstring anticipates exactly this
swap), so the change is contained.

### 3. Keycloak for identity

Real OIDC: login flow, user management UI, roles, token introspection, JWKS
rotation. Backend validates JWTs against Keycloak's JWKS endpoint and maps
realm roles onto route guards.

Roles:

| Role | Can |
|---|---|
| `admin` | everything + metrics/feedback dashboard + user management |
| `analyst` | chat, create/edit reports, submit corrections |
| `viewer` | chat, read reports; no writes |

Runs fully local in Docker with its own Postgres schema.

## Migration path

The riskiest part is not the new code — it is moving existing data without
losing it. One-shot, idempotent, reversible:

1. `scripts/migrate_to_postgres.py` — copies conversations, messages, feedback
   and corrections out of `chat.db` into Postgres. Assigns every existing
   `client_id` to a single `legacy` user so nothing is orphaned.
2. `scripts/migrate_reports_to_minio.py` — walks `reports/`, uploads each
   json/md pair, populates the `reports` catalog rows.
3. Both scripts are re-runnable (upsert on natural key) and leave the source
   data untouched, so a failed run costs nothing.

Rollback: the old SQLite file and `reports/` directory stay on disk until the
new path is verified.

## Work order

Sequenced so nothing is blocked and each step leaves the app runnable.

### Phase 1 — Data foundation
1. Add Postgres + MinIO to `docker-compose.yml`; health checks; named volumes.
2. SQLAlchemy models + Alembic migrations (`users`, `conversations`,
   `messages`, `corrections`, `reports`).
3. Port `ChatStore` to a Postgres-backed repository behind the **same method
   signatures**, so routers and the 63 existing tests are unaffected.
4. Run `migrate_to_postgres.py`; verify counts match.

### Phase 2 — Object storage
5. `app/shared/storage/` with an interface + `MinioStorage` implementation
   (mirrors the `app/shared/llm/` provider pattern already in the codebase).
6. Point `reports/service.py` at the storage interface; keep a filesystem
   implementation so tests can run without MinIO.
7. Bucket versioning + lifecycle policy; presigned URLs for downloads.
8. Run `migrate_reports_to_minio.py`.

### Phase 3 — Authentication
9. Keycloak container, realm + roles + clients as an importable realm JSON
   (so a teammate gets the same setup with one `up`).
10. `app/auth/` — JWT validation dependency, role guards, `current_user`.
11. Replace `X-Client-Id` with `user_id` from the token across all routes.
    Keep the header path behind a `AUTH_DISABLED=1` dev escape so tests and
    local iteration don't need a running Keycloak.
12. Frontend: OIDC login flow, token refresh, authenticated fetch wrapper.

### Phase 4 — Search
13. `tsvector` generated column on `messages` + GIN index; trigger to maintain.
14. `pgvector` column for message embeddings; reuse the existing embedding
    model already loaded for retrieval.
15. Hybrid search endpoint fusing FTS + vector with **RRF — reusing the exact
    fusion logic already written in `app/chatbot/bm25.py`**. The AI layer and
    the data layer become the same system.
16. Search UI: sidebar search box, ranked results with highlighted snippets,
    jump-to-message.

### Phase 5 — UI/UX
17. shadcn/ui + Radix on the existing Tailwind v4 setup (note: v4 needs the
    CSS-first config path, not `tailwind.config.js`).
18. **Core chat polish:** copy / regenerate / edit-and-resend, stop-generation,
    streaming cursor, auto-scroll with scroll-to-bottom pill, markdown tables,
    empty-state suggestion chips.
19. **Shell & navigation:** collapsible sidebar, conversations grouped by
    Today / Yesterday / Last 7 days, pinned chats, inline rename & delete,
    Cmd+K command palette, dark mode.
20. **Auth & profile surfaces:** login page, user menu + avatar, role-aware UI
    (admin-only metrics dashboard), per-user settings for model/temperature.

## What stays unchanged

- Ollama-only, fully local. No cloud LLM. The privacy constraint is unchanged.
- The `{metadata, blocks[]}` report contract — the integration seam between the
  two modules.
- The whole AI pipeline: retrieval, gates, hazard handling, security,
  evaluation harness. This work sits *underneath* it.
- The 63 backend tests must keep passing at every phase boundary.
