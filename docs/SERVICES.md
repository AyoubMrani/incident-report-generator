# Services — access, queries, and where the data goes

Practical guide to the three services added in the hardening work. For *why*
they were chosen, see [PLATFORM_HARDENING.md](PLATFORM_HARDENING.md).

```bash
docker compose -f infra/docker-compose.yml up -d      # start everything
docker compose -f infra/docker-compose.yml ps         # check health
docker compose -f infra/docker-compose.yml logs -f backend
```

| Service | URL | Credentials |
|---|---|---|
| App | http://localhost:8000 | `analyst` / `analyst` |
| Keycloak | http://localhost:8080 | `admin` / `admin` |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Postgres | `localhost:5433` | `ntt` / `ntt`, database `ntt` |

Port 5433, not 5432 — most dev machines already run a Postgres on the default.

---

## Postgres

### Connect

```bash
# From the host (needs psql installed)
psql postgresql://ntt:ntt@localhost:5433/ntt

# Without installing anything — psql inside the container
docker compose -f infra/docker-compose.yml exec postgres psql -U ntt -d ntt
```

### Look around

```sql
\dt                    -- list tables
\d messages            -- describe one table (columns, indexes, constraints)
\di                    -- list indexes
\q                     -- quit
```

Five tables: `users`, `conversations`, `messages`, `corrections`, `reports`.
(`alembic_version` is migration bookkeeping. Keycloak lives in its own
`keycloak` database, deliberately separate.)

### Useful queries

```sql
-- Who exists, and how much history each owns
SELECT u.username, u.provider, count(c.id) AS conversations
FROM users u LEFT JOIN conversations c ON c.user_id = u.id
GROUP BY u.id ORDER BY conversations DESC;

-- A user's recent conversations
SELECT c.title, c.updated_at, count(m.id) AS messages
FROM conversations c
JOIN users u ON u.id = c.user_id
LEFT JOIN messages m ON m.conversation_id = c.id
WHERE u.username = 'analyst'
GROUP BY c.id ORDER BY c.updated_at DESC LIMIT 10;

-- Read one conversation
SELECT role, left(text, 80) AS preview, to_timestamp(created_at) AS at
FROM messages WHERE conversation_id = '<id>' ORDER BY created_at;

-- Report catalog (metadata only — the content lives in MinIO)
SELECT incident_id, title, object_key, size_bytes
FROM reports WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 10;

-- Thumbs feedback
SELECT feedback, count(*) FROM messages
WHERE feedback IS NOT NULL GROUP BY feedback;
```

### Try the search Postgres actually runs

The keyword arm of hybrid search, by hand:

```sql
-- OR-ed terms (not AND) + ts_rank, matching app/db/search.py
SELECT c.title, ts_rank(m.search_vector, q) AS rank,
       ts_headline('english', m.text, q) AS snippet
FROM messages m
JOIN conversations c ON c.id = m.conversation_id,
     to_tsquery('english', 'dns | cache') q
WHERE m.search_vector @@ q
ORDER BY rank DESC LIMIT 5;
```

`search_vector` is a **generated column** — Postgres maintains it on every
write, so it cannot drift out of sync with the message text.

```sql
-- Semantic arm: how many messages have embeddings yet
SELECT count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded,
       count(*) AS total FROM messages;

-- Prove the index is used rather than a sequential scan
EXPLAIN ANALYZE
SELECT id FROM messages
WHERE search_vector @@ to_tsquery('english', 'dns');
```

### Backup and restore

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  pg_dump -U ntt ntt > backup.sql

cat backup.sql | docker compose -f infra/docker-compose.yml exec -T postgres \
  psql -U ntt -d ntt
```

### Migrations

Applied automatically at container start (entrypoint runs `alembic upgrade
head`). Manually, from `backend/`:

```bash
export DATABASE_URL=postgresql+psycopg://ntt:ntt@localhost:5433/ntt
alembic current                              # which revision is applied
alembic upgrade head                         # apply pending
alembic downgrade -1                         # roll back one
alembic revision --autogenerate -m "..."     # after editing app/db/models.py
```

> Autogenerate emits `pgvector.sqlalchemy.vector.VECTOR` without importing
> `pgvector` — add `import pgvector.sqlalchemy` to any generated migration that
> touches the `embedding` column, or it fails with `NameError` on a fresh
> database.

---

## MinIO

Report files (`.json` and `.md`) live here; their metadata lives in the
Postgres `reports` table. Blob = content, catalog = findability.

### Console

http://localhost:9001 → `minioadmin` / `minioadmin` → bucket `ntt-reports`.

Objects are keyed `reports/<incident-slug>/<filename>`, so everything about one
incident shares a prefix. **Versioning is on**: click an object → *Versions* to
see every save. That is the audit trail for a report edited after the incident
closed.

### CLI

```bash
alias mc='docker compose -f infra/docker-compose.yml run --rm minio-init mc'

mc ls local/ntt-reports/reports/                     # browse
mc ls --recursive local/ntt-reports/ | head
mc cat local/ntt-reports/reports/inc0012001/INC0012001_*.json
mc du local/ntt-reports                              # size
```

### From Python

```python
from app.shared.storage.factory import get_storage
storage = get_storage("minio")

storage.list("reports/")                    # objects under a prefix
storage.get("reports/inc42/report.json")    # bytes
storage.list_versions("reports/inc42/report.json")   # version history
storage.presigned_url("reports/inc42/report.json")   # temporary direct link
```

Set `STORAGE_BACKEND=filesystem` to fall back to plain files in `reports/` —
the rollback path, and what the test suite uses.

---

## Keycloak

### Admin console

http://localhost:8080 → `admin` / `admin` → switch realm (top-left) from
`master` to **`ntt`**.

The realm is defined in `infra/keycloak/realm-export.json` and imported on
first boot: three roles, one PKCE client, three seed users.

| Role | Can |
|---|---|
| `admin` | everything, plus the feedback/metrics endpoint |
| `analyst` | chat, create and edit reports, submit corrections |
| `viewer` | chat and read reports — **no writes** |

Seed users: `admin`/`admin`, `analyst`/`analyst`, `viewer`/`viewer`.

### Create a user (console)

1. Realm `ntt` → **Users** → *Add user*
2. Fill in username, email, **First name and Last name**, *Email verified* on
   → **Create**
3. **Credentials** tab → *Set password* → turn **Temporary off** (otherwise the
   user must change it at first login and the API password grant fails)
4. **Role mapping** tab → *Assign role* → filter by **realm roles** → pick
   `admin`, `analyst`, or `viewer` → **Assign**

> First and last name are **not optional**. The realm's `VERIFY_PROFILE` action
> requires them, and a user missing either cannot log in — Keycloak reports
> `Account is not fully set up`, which does not point at the real cause.

Nothing to do on the app side: the backend creates the local `users` row on
first request from a subject it has not seen.

### Create a user (CLI)

```bash
KC() { docker compose -f infra/docker-compose.yml exec keycloak \
       /opt/keycloak/bin/kcadm.sh "$@"; }

KC config credentials --server http://localhost:8080 \
   --realm master --user admin --password admin

# firstName and lastName are required — see the note above.
KC create users -r ntt -s username=ayoub -s enabled=true \
   -s email=ayoub@ntt.local -s emailVerified=true \
   -s firstName=Ayoub -s lastName=Aarab

KC set-password -r ntt --username ayoub --new-password 'secret' --temporary=false
KC add-roles -r ntt --uusername ayoub --rolename analyst

KC get users -r ntt --fields username,email,firstName,lastName   # verify
KC get-roles -r ntt --uusername ayoub                            # check roles
```

Confirm the account really works by asking for a token (below). A user that
lists correctly can still fail to authenticate.

### Delete a user

```bash
KC delete users/$(KC get users -r ntt -q username=ayoub --fields id \
  | grep '"id"' | sed 's/.*: "//;s/".*//') -r ntt
```

### Get a token to test the API

```bash
TOKEN=$(curl -s -X POST \
  http://localhost:8080/realms/ntt/protocol/openid-connect/token \
  -d client_id=ntt-platform -d grant_type=password \
  -d username=analyst -d password=analyst | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/me
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/reports
curl -s "http://localhost:8000/api/reports"          # 401 — no token
```

Inspect a token's claims at https://jwt.io, or:

```bash
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool
```

### Give an existing user someone's pre-auth history

Chats written before authentication belong to a browser UUID, not a person.
Linking them is a manual step on purpose — a browser id identifies a *browser*,
so guessing the owner could hand one person another's conversations.

```bash
export DATABASE_URL=postgresql+psycopg://ntt:ntt@localhost:5433/ntt
python scripts/migrate_to_postgres.py --list-users
python scripts/migrate_to_postgres.py --link-legacy test-client <oidc-subject>
```

### Running without Keycloak

`AUTH_DISABLED=1` restores the old `X-Client-Id` header identity — useful for
running the backend alone. The app **refuses to start** with this set when
`APP_ENV` is `production` or `staging`.

---

## Where the data actually goes

Follow one request end to end.

### Sending a chat message

| Step | File | What happens |
|---|---|---|
| 1 | [`auth/oidc.py:118`](../backend/app/auth/oidc.py#L118) | Token signature, expiry and issuer verified against Keycloak's JWKS |
| 2 | [`auth/dependencies.py:138`](../backend/app/auth/dependencies.py#L138) | Claims → `AuthContext`; `.id` is the OIDC subject |
| 3 | [`routers/chat.py`](../backend/app/routers/chat.py) `_client_id` | Identity resolved — the `X-Client-Id` header is *ignored* when auth is on |
| 4 | [`db/chat_repository.py:50`](../backend/app/db/chat_repository.py#L50) | Subject → `users` row (created on first sight) |
| 5 | [`db/chat_repository.py:240`](../backend/app/db/chat_repository.py#L240) | `INSERT INTO messages` — Postgres fills `search_vector` automatically |
| 6 | `chatbot/service.py` | RAG pipeline runs against the KB (Ollama, local) |
| 7 | step 5 again | Assistant reply stored with its structured answer in `payload` (JSONB) |

### Saving a report

| Step | File | What happens |
|---|---|---|
| 1 | [`routers/reports.py`](../backend/app/routers/reports.py) | `require_analyst` — a `viewer` gets 403 here |
| 2 | [`reports/storage_service.py:121`](../backend/app/reports/storage_service.py#L121) | JSON blob → MinIO (a new version if the key exists) |
| 3 | [`reports/storage_service.py:132`](../backend/app/reports/storage_service.py#L132) | Markdown sibling → MinIO |
| 4 | [`reports/storage_service.py:334`](../backend/app/reports/storage_service.py#L334) | Metadata upserted into the Postgres `reports` catalog |

Listing reports reads the **catalog** (one indexed query); opening one fetches
the **blob**. If the catalog ever falls behind, `reconcile()` rebuilds it from
the bucket — the blob is the source of truth for content.

### Searching chat history

| Step | File | What happens |
|---|---|---|
| 1 | [`db/search.py:182`](../backend/app/db/search.py#L182) | Keyword arm: `tsvector` + GIN, terms OR-ed, ranked by `ts_rank` |
| 2 | [`db/search.py:218`](../backend/app/db/search.py#L218) | Semantic arm: pgvector cosine distance (skipped if no embeddings) |
| 3 | [`shared/fusion.py`](../backend/app/shared/fusion.py) | Both rankings fused with RRF — the same function the KB retrieval uses |
| 4 | [`db/search.py:91`](../backend/app/db/search.py#L91) | Results hydrated with `ts_headline` snippets, scoped to the caller |

Every query joins through `conversations.user_id`; there is no unscoped search
path to call by accident.

### Quick reference

| Data | Lives in | Written by |
|---|---|---|
| Users, roles, passwords | Keycloak (its own `keycloak` DB) | Keycloak |
| Local user rows | Postgres `users` | `chat_repository._resolve_user` |
| Conversations, messages | Postgres | `chat_repository.add_message` |
| Corrections, thumbs | Postgres | `chat_repository` |
| Report content | MinIO `ntt-reports` | `storage_service.save` |
| Report metadata | Postgres `reports` | `storage_service._upsert_catalog_meta` |
| Embedding model cache | `hf-cache` volume | sentence-transformers |

---

## Troubleshooting

**Everything returns 401.** Keycloak is still booting (~30s). The backend
doesn't wait on it by design — JWKS is fetched lazily and tokens fail closed
until it answers. `docker compose logs keycloak` should end with `started in
Ns`.

**"port is already allocated" on 5432.** Another Postgres is running. This
stack uses 5433; change `POSTGRES_PORT` in `infra/.env` if that clashes too.

**Reports list is empty.** The catalog has no rows. Rebuild it from the bucket:

```bash
export DATABASE_URL=postgresql+psycopg://ntt:ntt@localhost:5433/ntt
python scripts/migrate_reports_to_minio.py --verify
```

**Signed in, but no conversations.** Correct behaviour — your history belongs
to the old browser id. See *Give an existing user someone's pre-auth history*.

**`invalid_grant: Account is not fully set up`** on a user you just created.
Almost always a missing **first or last name** — the realm's `VERIFY_PROFILE`
action requires both, and the error names neither. Fix:

```bash
KC update users/<id> -r ntt -s firstName=Ayoub -s lastName=Aarab
```

If names are present, check for a leftover required action
(`KC get users -r ntt -q username=<name> --fields requiredActions`) or a
password still marked temporary.

**Start completely fresh** (destroys all local data):

```bash
docker compose -f infra/docker-compose.yml down -v
docker compose -f infra/docker-compose.yml up -d --build
```
