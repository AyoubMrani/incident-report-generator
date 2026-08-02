#!/usr/bin/env bash
#
# reset.sh — put the platform back to a clean, first-run state.
#
# What "fresh" means here, and what it deliberately does NOT touch:
#
#   wiped   chat history (SQLite), embedding cache, answer cache (in-process,
#           so it dies with the container), the backend image
#   kept    reports/  — your knowledge base is real data, not scratch state
#   kept    the Ollama model cache — re-pulling llama3.2:3b is a multi-GB
#           download and has nothing to do with a stale app
#
# Usage:
#   scripts/reset.sh            # wipe local state, rebuild, start
#   scripts/reset.sh --hard          # also drop the HF embedding-model cache
#   scripts/reset.sh --no-start      # wipe only; don't rebuild or start
#   scripts/reset.sh --rebuild-deps  # also reinstall the ML stack (slow)
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

HARD=0
START=1
NOCACHE=0
for arg in "$@"; do
  case "$arg" in
    --hard)     HARD=1 ;;
    --no-start) START=0 ;;
    --rebuild-deps) NOCACHE=1 ;;
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

echo "==> Stopping containers and removing their volumes"
# -v drops the named volumes (chat-db, hf-cache): this is what actually clears
# conversation history. Note it does NOT remove images — that is why a plain
# `down -v && up` can still serve stale code. We force a rebuild below.
(cd infra && docker compose down -v --remove-orphans 2>/dev/null) || true

echo "==> Removing locally generated state"
rm -rf "$ROOT/backend/data/embed-cache"   # embeddings, rebuilt on next boot
rm -f  "$ROOT/data/chat.db" "$ROOT/data/chat.db-wal" "$ROOT/data/chat.db-shm"
rm -f  "$ROOT/backend/data/chat.db" "$ROOT/backend/data/chat.db-wal" \
       "$ROOT/backend/data/chat.db-shm"
find "$ROOT" -type d -name __pycache__ -not -path "*/node_modules/*" \
     -exec rm -rf {} + 2>/dev/null || true
rm -f "$ROOT/reports/report-export.html"

if [ "$HARD" = "1" ]; then
  echo "==> --hard: dropping the embedding-model cache (re-downloads ~90MB)"
  rm -rf "$ROOT/backend/.cache" "$HOME/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2"
fi

echo "==> Reports left intact: $(ls -1 "$ROOT"/reports/*.json 2>/dev/null | wc -l | tr -d ' ') json files"

if [ "$START" = "0" ]; then
  echo "==> Done (not starting; --no-start)"
  exit 0
fi

# A normal rebuild already picks up every source change, because the COPY layer
# is invalidated by the edit. --no-cache additionally reinstalls torch and
# sentence-transformers, which takes many minutes and is almost never what you
# want; it is behind --rebuild-deps for the rare case a dependency is corrupt.
cd "$ROOT/infra"

if [ "$NOCACHE" = "1" ]; then
  echo "==> Rebuilding from scratch (--rebuild-deps: reinstalls the ML stack, slow)"
else
  echo "==> Rebuilding the image (--build is required: 'down -v' keeps old images)"
fi

# Plain string, not an array: macOS ships bash 3.2, where `"${arr[@]}"` on an
# empty array trips `set -u` as an unbound variable. There is exactly one
# optional flag here and it contains no spaces, so word splitting is safe.
build_backend() {
  if [ "$NOCACHE" = "1" ]; then
    docker compose build --no-cache backend
  else
    docker compose build backend
  fi
}

# A failed build must never look like a successful reset. Run it directly
# rather than in a `( … )` subshell: a subshell's non-zero exit does not trip
# `set -e` in the parent when it is the last statement of a branch, which is
# exactly how this script once exited 0 while leaving nothing running.
# Retry once: the pip install pulls several hundred MB, and a transient network
# error mid-download fails the whole build. Observed in practice — a plain retry
# succeeded with no other change.
if ! build_backend; then
  echo
  echo "==> Build failed; retrying once (this is usually a network hiccup)"
  if ! build_backend; then
    echo
    echo "!! Build FAILED twice — the previous image (if any) is still on disk,"
    echo "   but the containers are down. Nothing is running. Fix the build,"
    echo "   then re-run:  scripts/reset.sh"
    exit 1
  fi
fi

echo "==> Starting"
if ! docker compose up -d --force-recreate; then
  echo "!! Failed to start the containers. Logs: docker compose -f infra/docker-compose.yml logs backend"
  exit 1
fi

cd "$ROOT"

echo "==> Waiting for the knowledge base to index"
for i in $(seq 1 120); do
  if curl -s -m 3 http://localhost:8000/api/health 2>/dev/null | grep -q '"chatbot_ready":true'; then
    echo "    ready after ${i}s"
    curl -s http://localhost:8000/api/health; echo
    exit 0
  fi
  sleep 1
done

echo "!! Backend did not become ready in 120s. Last log lines:"
(cd "$ROOT/infra" && docker compose logs --tail 30 backend) || true
echo
echo "   If this mentions Ollama, start it with:  ollama serve"
exit 1
