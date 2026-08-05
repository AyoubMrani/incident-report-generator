# Platform Hardening

Branch: `platform-hardening` (off `main` @ `4dada6f`).
`main` holds the presented version and is not touched by this work.

**Status: all five phases complete.** 414 backend tests pass with Postgres,
MinIO and Keycloak running (0 skipped); the frontend builds. See
[What shipped](#what-shipped) for the per-phase result and the bugs the real
data exposed.

## Quick start

```bash
cp infra/.env.example infra/.env          # defaults work as-is for local use
docker compose -f infra/docker-compose.yml up --build

# One-time, to bring existing data across:
export DATABASE_URL=postgresql+psycopg://ntt:ntt@localhost:5433/ntt
python scripts/migrate_to_postgres.py           # chat history  -> Postgres
python scripts/migrate_reports_to_minio.py      # report blobs  -> MinIO

# Pre-auth history belongs to a browser id, not a person. Attach it to an
# account deliberately (see the note under Phase 3):
python scripts/migrate_to_postgres.py --list-users
python scripts/migrate_to_postgres.py --link-legacy <client-id> <oidc-subject>
```

Sign in at http://localhost:8000 with `analyst` / `analyst`
(also `admin` / `admin`, `viewer` / `viewer` — seeded by the realm import).

| Service | URL | Notes |
|---|---|---|
| App | http://localhost:8000 | FastAPI serves the built SPA |
| Keycloak | http://localhost:8080 | admin console: `admin` / `admin` |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Postgres | `localhost:5433` | 5433, not 5432 — see below |

Running the backend alone, without Keycloak: `AUTH_DISABLED=1`. That flag is
refused at boot when `APP_ENV` is `production` or `staging`.

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

## What shipped

All five phases, in order, each leaving the app runnable and the suite green.

### Phase 1 — Postgres foundation

`users`, `conversations`, `messages`, `corrections`, `reports`, under Alembic.
`ChatRepository` keeps the SQLite store's exact method signatures, so the swap
was one line in `main.py` and no router or existing test changed.

Two schema choices worth knowing: `messages.search_vector` is a **generated
column**, not trigger-maintained, so a bulk insert cannot leave the index out
of sync with the text; and Postgres is mapped to host port **5433**, because a
developer machine usually already has one on 5432.

*Bug the real data found.* The obvious port of `relevant_corrections` uses
`websearch_to_tsquery`, which **ANDs** its terms — so asking "dns cache
clearing steps" silently stopped matching a stored correction for "how do I
clear the DNS cache?" because "steps" was absent. The SQLite version scored
token overlap, so the faithful port is OR plus `ts_rank`: recall from the OR,
precision from the ranking. The parity test that caught it runs against both
stores.

### Phase 2 — Object storage

Blobs in MinIO (versioned), metadata in a Postgres catalog. Listing is one
indexed query instead of a directory scan plus a JSON parse per file. The
filesystem backend remains a first-class implementation — it is what the test
suite runs on, and the rollback path.

*Two bugs the real corpus found, both silently lossy:*

- Key validation started as `[A-Za-z0-9._/-]` and **rejected 80 of the 93
  report files**, because the real naming convention is `INC0012001_VPN clients
  unable to establish tunnel.json` — spaces and all, which S3 permits. The rule
  now enforces what actually matters (no absolute paths, no `..`, no control
  characters) and stays permissive otherwise.
- The catalog made `incident_id` unique among live rows. **Eight incident ids
  appear in two files each**, so that constraint would have dropped one file
  from every pair. Uniqueness moved to `object_key`, which is genuinely
  one-to-one with a blob.

`reconcile()` validates metadata rather than the whole report: 16 reports have
a malformed code block, and requiring a full `IncidentReport` would have made
them invisible in the UI even though the filesystem service listed them fine.

### Phase 3 — Authentication

Keycloak issues RS256 tokens; the backend verifies them against the published
JWKS. No shared secret exists to leak, and a token cannot be forged by editing
its payload — there is a test that tries. The realm (roles, PKCE client, three
seed users) is committed as `infra/keycloak/realm-export.json`.

Auth is declared **at the router**, not per endpoint.

*What the audit found.* Probing every route without a token exposed **ten
unauthenticated endpoints** — the entire reports surface, including
`DELETE /api/delete/{filename}` answering **200**. Anyone who could reach the
port could destroy incident records. Source inspection had missed it because
the handlers looked fine. A test now enumerates the live route table and fails
if any endpoint answers anything but 401/403, so a new route is protected by
default rather than exposed by omission.

Both the container-internal and browser-facing issuer URLs are accepted: the
`iss` claim carries whichever the browser used, so validating only
`http://keycloak:8080` rejects every real login.

### Phase 4 — Hybrid search

Keyword (`tsvector` + GIN) and semantic (pgvector) rankings fused with RRF.
The fusion is not a second implementation — it moved out of
`chatbot/retrieval.py` into `shared/fusion.py`, and both callers use it, so the
KB retrieval and the history search cannot drift apart.

Each arm covers the other's blind spot, and the tests demonstrate it rather
than assert it: keyword finds `IKE phase 1` and `resolvectl flush-caches`,
where dense vectors are weakest since every incident number embeds to roughly
the same place; semantic answers *"database lock contention at peak traffic"*
with a conversation about *"recurring deadlocks on the orders table during the
flash sale"* — no shared word.

Embeddings are optional and backfilled out of band. With no model loaded the
semantic arm returns nothing and search degrades to keyword-only. The embedder
is the chatbot's existing model, attached after it loads, so search never puts
a second copy in memory.

### Phase 5 — Frontend

OIDC Authorization Code + PKCE written directly against the browser crypto API
(~150 lines) rather than adding `oidc-client-ts` or `keycloak-js`, which hide
the redirect handling that is the part worth reading when a login loop breaks.

Three token details that are easy to get wrong: only the refresh token is
persisted, in **sessionStorage** (localStorage survives tab close and stays
readable by any XSS for the token's lifetime); concurrent refreshes are
collapsed into one in-flight promise, because Keycloak rotates refresh tokens
and parallel redemptions would log the user out; and `authFetch` retries once
after a refresh on 401, since a token can expire between the client's skew
check and the server validating it.

Plus Cmd-K search with per-result badges showing which arm matched — when a
result shares no words with the query, that badge is the only thing explaining
why it is there — and CSS-first dark mode, as Tailwind v4 requires, with an
inline script applying the class before first paint.

*What signing in revealed.* The analyst account showed **zero conversations** —
correct behaviour, and confirmation that isolation works: the 26 migrated chats
belonged to the browser UUID `test-client`, not to a Keycloak subject. Linking
them is `--link-legacy`, a deliberate operator step and never an inference. A
browser id identifies a browser, not a person; guessing would hand one person
another person's history.

## Verified

With Postgres, MinIO and Keycloak running:

- **414 backend tests pass, 0 skipped.** Integration tests genuinely exercise
  all three services; they skip only when a service is down.
- **Data migrated intact.** All 26 conversations and 52 messages readable
  through the API with no missing rows, changed titles or message-count drift.
  93 report files uploaded, 0 missing, 0 content mismatches by SHA-256, 70
  catalog rows for 70 reports. Re-runs upload nothing, so version history stays
  an edit trail rather than a log of migrations.
- **Against a real uvicorn:** 401 unauthenticated; 70 reports served from MinIO
  through the catalog; 26 conversations visible and searchable as `analyst`, 0
  as `viewer`; `viewer` gets 403 on delete while keeping read access.
- **Frontend builds.** Typechecking reports the same 8 pre-existing errors as
  before this work — all in the report-generator module, none in the new code.

## Production hardening

- **Migrations run at boot** (`alembic upgrade head` in the entrypoint) and a
  failure is fatal. Booting against a mismatched schema surfaces later as
  scattered column errors on whichever request touches the missing column
  first; refusing to start points at the real problem immediately.
- **CORS is environment-aware.** Empty by default (FastAPI serves the SPA from
  one origin); the Vite dev origin is allowed only when `APP_ENV` is a
  development one, and `CORS_ORIGINS` covers a separately-hosted frontend.
  Methods and headers are enumerated rather than `*`.
- **`AUTH_DISABLED=1` is refused** when `APP_ENV` is production or staging. A
  misconfiguration that fails at boot is recoverable; one that quietly serves
  an unauthenticated API is a breach.
- **`infra/.env.example`** documents every knob and flags the two sets of
  credentials that must change before this runs anywhere but a laptop.
- The container still runs as a **non-root uid** with the entrypoint handing
  over volume ownership before dropping privileges (pre-existing, preserved).

## Known gaps

Deliberately out of scope, listed so they are choices rather than oversights:

- **Keycloak runs in `start-dev`** — HTTP, no hostname strictness. Correct for
  a local-only stack; a deployed one needs `start --optimized` with TLS.
- **Default credentials in compose.** Fine for a laptop, listed in
  `.env.example` as the first thing to change.
- **Tokens in `sessionStorage`.** A cookie-based BFF would be stronger but
  needs a server-side session store this stack deliberately does not have.
- **No rate limiting** on the auth or chat endpoints.
- **Bundle is 610 KB** (173 KB gzipped) in one chunk; code-splitting the report
  editor would be the obvious first cut.
- **8 pre-existing TypeScript errors** in the report-generator module, left
  alone because that module is explicitly not ours to refactor.

## What stays unchanged

- Ollama-only, fully local. No cloud LLM. The privacy constraint is unchanged.
- The `{metadata, blocks[]}` report contract — the integration seam between the
  two modules.
- The whole AI pipeline: retrieval, gates, hazard handling, security,
  evaluation harness. This work sits *underneath* it. The one change inside it
  was moving RRF into `shared/fusion.py` so the history search reuses it; the
  69 retrieval tests pass unchanged, which is the evidence that the extraction
  preserved behaviour.
- The pre-existing test suite kept passing at every phase boundary. It started
  at **269** tests (not the 63 this plan first claimed — that figure was stale)
  and ends at **414**, all passing.
