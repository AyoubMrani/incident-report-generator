#!/usr/bin/env bash
# Run the app with the project venv (mlx_vlm + streamlit live here).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create it and install deps:"
  echo "  cd $ROOT"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "$ROOT/.venv/bin/python" -c "import streamlit" 2>/dev/null; then
  echo "Installing dependencies into $ROOT/.venv …"
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
fi

exec "$ROOT/.venv/bin/python" -m streamlit run Rapp.py "$@"
