STG app

Primary entrypoint:
`/Users/ayoub/work/STG/stg_app/Rapp.py`

Legacy backup entrypoints:
- `stg_app/backup/app.py`
- `stg_app/backup/app_mlx.py`

First-time setup (only if `.venv` is new or incomplete):

```bash
cd /Users/ayoub/work/STG/stg_app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run (always use the **stg_app** `.venv` — streamlit + mlx_vlm live here):

```bash
cd /Users/ayoub/work/STG/stg_app
./run.sh
```

`./run.sh` will run `pip install -r requirements.txt` automatically if Streamlit is missing.

Equivalent:

```bash
/Users/ayoub/work/STG/stg_app/.venv/bin/python -m streamlit run Rapp.py
```

### Vision (VLM) not working?

If you see `mlx_vlm is not importable`, Streamlit is almost always using the **wrong Python** (e.g. conda base) instead of `stg_app/.venv`.

1. Check the sidebar **Python interpreter** path in the app.
2. Stop Streamlit and start again with `./run.sh` or the command above.
3. Verify in a terminal:

```bash
/Users/ayoub/work/STG/stg_app/.venv/bin/python -c "import mlx_vlm; print('ok')"
```

Weights must exist at `stg_app/models/qwen2.5-vl-7b-4bit-vlm/` (see `incident_chatbot/config.py`).

Project structure:
- `stg_app/incident_chatbot/` — modular application code split by concern
- `stg_app/reports/` — generated incident reports in `.json` and `.md`
- `stg_app/docs/` — kept empty for legacy compatibility only
- `incident-report-generator/` — untouched third-party report generator

Notes:
- Use `incident-report-generator` to create documentation dynamically.
- Export every generated report in both Markdown (`.md`) and JSON (`.json`) formats.
- The old static Word document has been removed from `stg_app/docs/`.
