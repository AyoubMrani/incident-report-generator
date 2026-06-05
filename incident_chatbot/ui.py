"""
ui.py — Streamlit interface

Tabs:
  Chat       — main flow: input → understand → search → guided resolution + report list
  Knowledge  — inspect what is indexed (sidebar search)
  VLM Test   — raw vision model sandbox
"""

import os
import sys
import tempfile

import streamlit as st
from PIL import Image, ImageDraw

from incident_chatbot.config   import TOP_K
from incident_chatbot.ingestion import build_knowledge_base
from incident_chatbot.retrieval import search
from incident_chatbot.config    import (
    CONFIDENCE_THRESHOLD as KB_CONFIDENCE_THRESHOLD,
    EMBED_MODEL_NAME,
    OLLAMA_MODEL,
    QWEN_MLX_PATH,
    REPORTS_FOLDER,
)
from incident_chatbot.llm       import (
    VLMUnavailableError,
    understand_text,
    understand_screenshot,
    ask_ollama,
    vlm_status,
)
from incident_chatbot.prompts   import RESOLUTION_PROMPT, FALLBACK_PROMPT, VLM_UNDERSTAND_PROMPT
from incident_chatbot.resolution import (
    format_retrieval_context,
    parse_resolution,
    render_guided_steps,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_write(uploaded):
    suffix = os.path.splitext(uploaded.name or ".png")[1] or ".png"
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(uploaded.getvalue())
    f.flush()
    return f.name

def _tmp_save(img: Image.Image) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(f, format="PNG")
    return f.name

def _score_badge(score: float) -> str:
    pct = int(score * 100)
    if pct >= 80:
        return f"🟢 {pct}%"
    if pct >= 60:
        return f"🟡 {pct}%"
    return f"🔴 {pct}%"

# ── Dev sidebar ───────────────────────────────────────────────────────────────

def _render_dev_sidebar(n_files: int, n_chunks: int):
    st.sidebar.markdown("### Dev runtime")
    st.sidebar.caption("Internal NRI assistant — not for end users.")
    st.sidebar.markdown("**Python interpreter**")
    st.sidebar.code(sys.executable, language=None)

    vlm = vlm_status()
    if vlm["ready"]:
        st.sidebar.success("Vision: ready")
    elif vlm["package_installed"]:
        st.sidebar.warning("Vision: mlx_vlm OK — weights missing")
        st.sidebar.caption(vlm["reason"])
        if vlm.get("hint"):
            st.sidebar.caption(vlm["hint"])
    else:
        st.sidebar.error("Vision: mlx_vlm not in this interpreter")
        st.sidebar.caption(vlm["reason"])
        app_venv = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv", "bin", "python")
        if os.path.isfile(app_venv) and os.path.realpath(app_venv) != os.path.realpath(sys.executable):
            st.sidebar.markdown("**Likely fix** — restart with the project venv:")
            st.sidebar.code(f"{app_venv} -m streamlit run Rapp.py", language="bash")
            st.sidebar.caption("Or: `./run.sh` from the stg_app folder.")
        elif vlm.get("hint"):
            st.sidebar.code(vlm["hint"], language="bash")

    st.sidebar.code(
        f"embed: {EMBED_MODEL_NAME}\n"
        f"ollama: {OLLAMA_MODEL}\n"
        f"reports: {REPORTS_FOLDER}\n"
        f"retrieval threshold: {KB_CONFIDENCE_THRESHOLD}\n"
        f"vlm path: {QWEN_MLX_PATH}",
        language=None,
    )
    st.sidebar.metric("Indexed files", n_files)
    st.sidebar.metric("Chunks", n_chunks)


def _vision_failure_message(exc: VLMUnavailableError) -> str:
    """User-facing vision error — no install nag when mlx_vlm is already present."""
    if exc.package_installed:
        return f"Vision analysis failed: {exc.reason}"
    return f"Vision analysis unavailable: {exc.reason}. {exc.hint}"


def _analyze_uploaded_image(uploaded) -> tuple[str, str]:
    """
  Run VLM on an upload. Returns (combined_problem_text, image_analysis_for_prompt).
  Raises VLMUnavailableError when vision cannot run.
    """
    tmp_path = _tmp_write(uploaded)
    try:
        vlm_out = understand_screenshot(tmp_path)
        return vlm_out, vlm_out
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Report list ───────────────────────────────────────────────────────────────

def render_report_list(results: list[dict]):
    st.subheader("Retrieval hits")
    st.caption(
        "Embedding-ranked chunks. Use scores and `SOURCE` paths to debug mismatches."
    )

    for i, r in enumerate(results):
        # header = f"{_score_badge(r['score'])}  **{r['title']}**  —  `{r['source']}`"
        with st.expander(f"{r['title']} — `{r['source']}`", expanded=(i == 0)):
            st.markdown("**Most relevant excerpt:**")
            excerpt = r["text"]
            st.code(excerpt[:800] + ("…" if len(excerpt) > 800 else ""), language=None)

            # Surface code blocks from JSON reports so SQL is immediately visible
            path = r.get("path", "")
            if os.path.exists(path) and path.endswith(".json"):
                try:
                    import json
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    code_blocks = [
                        b for b in data.get("blocks", [])
                        if b.get("type") == "code" and b.get("content", "").strip()
                    ]
                    if code_blocks:
                        st.markdown("**Code blocks in this report:**")
                        for cb in code_blocks:
                            lang = cb.get("language") or "sql"
                            st.code(cb["content"].strip(), language=lang)
                except Exception:
                    pass

# ── Main app ──────────────────────────────────────────────────────────────────

def run():
    st.set_page_config(page_title="NRI Incident Assistant (dev)", layout="wide")
    st.title("NRI Incident Assistant")
    st.caption(
        "Incident copilot for engineers: text only, screenshot only, or both — plus retrieval debug output."
    )

    # Load knowledge base once
    try:
        embed_model, embeddings, documents, metadata, n_files = build_knowledge_base()
    except Exception as e:
        st.sidebar.error(str(e))
        st.error(f"Knowledge base error — check your reports/ folder: {e}")
        st.stop()

    _render_dev_sidebar(n_files, len(documents))
    vision = vlm_status()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    chat_tab, kb_tab, vlm_tab = st.tabs(["Resolve", "Index", "Vision"])

    # ── CHAT ─────────────────────────────────────────────────────────────────
    with chat_tab:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            user_text = st.text_area(
                "Incident text",
                height=160,
                placeholder=(
                    "Logs, stack traces, ServiceNow text, SQL, commands, home IDs, "
                    "status codes — or leave empty if the screenshot carries the context."
                ),
            )

        with col_right:
            uploaded = st.file_uploader(
                "Screenshot / image",
                type=["png", "jpg", "jpeg", "webp"],
                help="Ticket UI, DBeaver, dashboards, alerts, terminals, Excel highlights.",
            )
            if uploaded:
                st.image(Image.open(uploaded).convert("RGB"), use_column_width=True)
            elif not vision["package_installed"]:
                st.caption(
                    "Vision uses local Qwen2.5-VL (mlx_vlm). "
                    "Package not detected in this interpreter — see sidebar."
                )
            else:
                st.caption(
                    "Upload an error UI, ticket, SQL client, or dashboard for vision analysis."
                )

        go = st.button("Run retrieval + resolution", type="primary")

        if go:
            has_text = bool(user_text.strip())
            has_image = uploaded is not None

            if not has_text and not has_image:
                st.warning("Provide incident text, a screenshot, or both.")
                st.stop()

            problem = ""
            image_analysis = "None"

            # Step 1 — vision (when image present) then text understanding
            with st.spinner("Analyzing input…"):
                if has_image:
                    try:
                        with st.spinner("Running vision model…"):
                            vlm_text, image_analysis = _analyze_uploaded_image(uploaded)
                        with st.expander("Vision extraction", expanded=True):
                            st.write(vlm_text)
                        problem = (
                            f"{user_text.strip()}\n\n{vlm_text}".strip()
                            if has_text
                            else vlm_text
                        )
                    except VLMUnavailableError as exc:
                        st.error(_vision_failure_message(exc))
                        if not has_text:
                            st.stop()
                        problem = user_text.strip()
                        image_analysis = "None"
                else:
                    problem = user_text.strip()
                    if vision["ready"]:
                        st.info(
                            "Investigating from text. "
                            "Upload a screenshot of the error, dashboard, ticket, or SQL client "
                            "if you want vision analysis included."
                        )

                if problem:
                    with st.spinner("Building retrieval query (Ollama)…"):
                        understood = understand_text(problem)
                else:
                    st.error("Could not build a problem description from the input.")
                    st.stop()

            with st.expander("Retrieval query (Ollama)", expanded=True):
                st.write(understood)

            # Step 2 — search
            with st.spinner("Searching knowledge base…"):
                results = search(understood, embed_model, embeddings, documents, metadata, top_k=TOP_K)

            if not results:
                st.warning("No documents in knowledge base. Add reports to the reports/ folder.")
                st.stop()

            top_score = results[0]["score"]
            if top_score < KB_CONFIDENCE_THRESHOLD:
                st.caption(
                    f"Top retrieval similarity {int(top_score * 100)}% — "
                    "expert resolution will still be generated from best available matches."
                )

            # Step 3 — resolution
            st.divider()
            st.subheader("Expert resolution")

            with st.spinner("Generating resolution (Ollama)…"):
                knowledge = format_retrieval_context(results, limit=TOP_K)
                raw = ask_ollama(
                    RESOLUTION_PROMPT.format(
                        problem=understood,
                        image_analysis=image_analysis,
                        knowledge=knowledge,
                    )
                )
                parsed = parse_resolution(raw)
                with st.expander("Parsed JSON", expanded=False):
                    st.json({
                        k: parsed[k]
                        for k in parsed
                        if k not in ("raw", "steps", "warnings", "missing")
                    })
                render_guided_steps(parsed)

            # Step 4 — similar reports
            st.divider()
            render_report_list(results)

    # ── KNOWLEDGE BASE ────────────────────────────────────────────────────────
    with kb_tab:
        from collections import Counter
        st.metric("Total chunks", len(documents))

        counts = Counter(m["source"] for m in metadata)
        st.subheader("Indexed files")
        for src, n in sorted(counts.items()):
            st.write(f"- `{src}` — {n} chunks")

        st.divider()
        st.subheader("Search the knowledge base directly")
        q = st.text_input("Query", placeholder="delete provision status")
        if q:
            hits = search(q, embed_model, embeddings, documents, metadata, top_k=5)
            for h in hits:
                # with st.expander(f"{_score_badge(h['score'])} {h['title']} — `{h['source']}`"):
                with st.expander(f"{h['title']} — `{h['source']}`"):
                    st.text(h["text"][:500])

    # ── VLM TEST ──────────────────────────────────────────────────────────────
    with vlm_tab:
        vlm = vlm_status()
        if vlm["ready"]:
            st.success("mlx_vlm importable · weights on disk · inference ready")
        elif vlm["package_installed"]:
            st.warning(vlm["reason"])
            if vlm.get("hint"):
                st.caption(vlm["hint"])
        else:
            st.error(vlm["reason"])
            if vlm.get("hint"):
                st.code(vlm["hint"], language="bash")

        vlm_prompt = st.text_area("Prompt", value=VLM_UNDERSTAND_PROMPT, height=140)
        max_tok = st.slider("Max tokens", 64, 512, 256, 32)
        up = st.file_uploader("Image", type=["png", "jpg", "jpeg", "webp"], key="vlm_img")

        c1, c2 = st.columns(2)
        run_up    = c1.button("Run on image",    disabled=up is None)
        run_smoke = c2.button("Smoke test")

        img_path = None
        if up:
            st.image(Image.open(up).convert("RGB"), use_column_width=True)
            img_path = _tmp_write(up)

        if run_smoke:
            smoke = Image.new("RGB", (640, 320), "#f0f4f8")
            d = ImageDraw.Draw(smoke)
            d.rounded_rectangle((30, 30, 610, 290), radius=20, fill="#dbe9f9",
                                 outline="#2c3e50", width=3)
            d.text((60, 260), "VLM smoke test image", fill="#1f2937")
            img_path = _tmp_save(smoke)
            st.image(smoke, use_column_width=True)

        if (run_up or run_smoke) and img_path:
            from incident_chatbot.llm import run_vlm
            try:
                with st.spinner("Running vision model…"):
                    out = run_vlm(vlm_prompt, image_path=img_path, max_tokens=max_tok)
                st.subheader("Output")
                st.write(out)
            except VLMUnavailableError as e:
                st.error(_vision_failure_message(e))
            except Exception as e:
                st.exception(e)
            finally:
                if img_path and os.path.exists(img_path):
                    os.unlink(img_path)

def main():
    run()