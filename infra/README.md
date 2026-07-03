# infra — running the whole app with one command

```bash
# from the repo root
docker compose -f infra/docker-compose.yml up --build
```

Then open **http://localhost:8000** — the FastAPI backend serves the built React
SPA (chatbot + report generator) on that one port.

## What the image does

`Dockerfile.backend` is multi-stage:

1. **frontend stage** (`node:20`) runs `npm ci && npm run build` → `frontend/dist`
2. **backend stage** (`python:3.11`) installs `backend/requirements.txt`, copies
   the app, and copies `frontend/dist` in so FastAPI serves it as static files.

No host-side `npm` or `python` needed — everything builds inside the image.

## LLM (Ollama)

By default the backend talks to **Ollama running on your host**
(`host.docker.internal:11434`), because:

- you already run `ollama serve` with `llama3:8b` and `qwen2.5vl:3b` pulled, and
- on macOS the host Ollama gets Metal GPU acceleration, while a containerized
  one would be CPU-only and start empty.

So keep `ollama serve` running on the host and you're set.

**Alternative — Ollama in a container** (Linux, or if you don't want host Ollama):

```bash
docker compose -f infra/docker-compose.yml --profile with-ollama up --build
docker compose -f infra/docker-compose.yml exec ollama ollama pull llama3:8b
docker compose -f infra/docker-compose.yml exec ollama ollama pull qwen2.5vl:3b
```

and change the backend's `OLLAMA_HOST` to `http://ollama:11434` in
`docker-compose.yml`.

## Volumes

- `../reports:/data/reports` — the shared report data (the integration seam),
  bind-mounted so reports created in the app land in the repo's `reports/`.
- `hf-cache` — persists the `all-MiniLM-L6-v2` embedding model between restarts
  (otherwise it re-downloads on every boot).
- `ollama-models` — persists pulled models (only with the `with-ollama` profile).

## Config knobs (env on the `backend` service)

| Var | Default | Meaning |
|---|---|---|
| `REPORTS_DIR` | `/data/reports` | where reports are read/written |
| `CHATBOT_PROVIDER` | `ollama` | LLM provider (`ollama` or `gemini`) |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama endpoint |
| `DISABLE_CHATBOT` | unset | set `1` to boot reports-only (skips model load) |
| `GEMINI_API_KEY` | unset | required only if `CHATBOT_PROVIDER=gemini` |
