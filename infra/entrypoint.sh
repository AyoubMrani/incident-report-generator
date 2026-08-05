#!/bin/sh
#
# entrypoint.sh — fix volume ownership, then drop to the unprivileged user.
#
# Docker creates named volumes root-owned at *mount* time, which masks any
# chown done during the build. So the container has to start as root, hand the
# mounted paths to appuser, and only then exec the app as appuser. The Python
# process itself never runs as root, which is the property we actually want.
#
# Bind mounts (reports/) keep their host ownership by design — chown would
# rewrite the developer's own files on the host. If that path is not writable,
# say so clearly instead of failing later with a confusing SQLite error.
set -eu

APP_UID=10001

# Apply database migrations before the app starts.
#
# Compose already waits for Postgres to be *healthy*, but healthy means
# "accepting connections", not "schema is current" — so this runs here rather
# than relying on ordering alone.
#
# A failure is fatal on purpose. The alternative is booting against a schema
# the code does not match, which surfaces later as scattered column errors on
# whichever request happens to touch the missing column first; refusing to
# start points at the real problem immediately.
#
# Skipped when DATABASE_URL is unset (the SQLite-only configuration), and
# skippable with SKIP_MIGRATIONS=1 for the case where an operator applies them
# out of band.
run_migrations() {
    if [ -z "${DATABASE_URL:-}" ] || [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then
        return 0
    fi
    echo "applying database migrations..."
    if ! alembic upgrade head; then
        echo "ERROR: database migrations failed; refusing to start." >&2
        echo "       Fix the database or set SKIP_MIGRATIONS=1 to bypass." >&2
        exit 1
    fi
}

if [ "$(id -u)" = "0" ]; then
    for dir in /data/chat /data/hf-cache /data/embed-cache; do
        mkdir -p "$dir"
        chown -R "$APP_UID:$APP_UID" "$dir" 2>/dev/null || true
    done

    # reports/ is usually a bind mount from the host. Only take ownership when
    # it is empty (a fresh named volume); never rewrite a populated host dir.
    if [ -d /data/reports ] && [ -z "$(ls -A /data/reports 2>/dev/null)" ]; then
        chown "$APP_UID:$APP_UID" /data/reports 2>/dev/null || true
    fi

    if ! setpriv --reuid="$APP_UID" --regid="$APP_UID" --init-groups \
         test -w /data/reports 2>/dev/null; then
        echo "WARNING: /data/reports is not writable by uid $APP_UID." >&2
        echo "         Saving reports will fail. On Linux, either run the container" >&2
        echo "         with 'user: \"\$(id -u):\$(id -g)\"' in docker-compose.yml, or" >&2
        echo "         chown the host reports/ directory to uid $APP_UID." >&2
    fi

    run_migrations

    # setpriv, not su: it execs into the target process rather than forking it,
    # so uvicorn becomes PID 1 and receives SIGTERM directly. Under `su`, PID 1
    # is su itself, which does not forward signals — `docker stop` would then
    # fall through to SIGKILL after the timeout instead of shutting down
    # cleanly (dropping in-flight SSE streams and risking a torn SQLite write).
    exec setpriv --reuid="$APP_UID" --regid="$APP_UID" --init-groups "$@"
fi

# Already unprivileged (e.g. compose set `user:`): just run.
run_migrations
exec "$@"
