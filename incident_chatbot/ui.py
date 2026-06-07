"""
ui.py — Streamlit interface (cross-platform)

Tabs:
  Chat          — main flow: input → understand → search → guided resolution + report list
  Knowledge     — inspect indexed files + direct KB search
  VLM Test      — raw vision model sandbox (Ollama-backed, works on Windows/macOS/Linux)
"""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from incident_chatbot.config    import TOP_K, CONFIDENCE_THRESHOLD, OLLAMA_VISION_MODEL
from incident_chatbot.ingestion import build_knowledge_base
from incident_chatbot.retrieval import combine_retrieval_queries, search, search_multimodal
from incident_chatbot.llm       import (
    understand_text,
    understand_screenshot,
    ask_ollama,
    run_vlm,
    vlm_status,
)
from incident_chatbot.prompts   import (
    RESOLUTION_PROMPT,
    FALLBACK_PROMPT,
    VLM_UNDERSTAND_PROMPT,
    RESOLUTION_PROMPT_REQUIRED,
    FALLBACK_PROMPT_REQUIRED,
    NO_IMAGE_ANALYSIS,
    format_prompt,
)
from incident_chatbot.resolution import (
    format_retrieval_context,
    parse_resolution,
    render_guided_steps,
)


# ── File helpers (cross-platform) ─────────────────────────────────────────────

def _tmp_write(uploaded) -> str:
    """Save an uploaded Streamlit file to a temp path. Works on Windows."""
    suffix = Path(uploaded.name or "upload.png").suffix or ".png"
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(uploaded.getvalue())
    f.flush()
    f.close()           # close before reading on Windows (no delete-on-close)
    return f.name


def _tmp_save(img: Image.Image) -> str:
    """Save a PIL image to a temp PNG. Works on Windows."""
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(f, format="PNG")
    f.flush()
    f.close()
    return f.name


# ── UI helpers ────────────────────────────────────────────────────────────────

# def _score_badge(result: dict) -> str:
#     """Show a rank-relative match strength so similar reports cluster visually."""
#     semantic = result.get("semantic_score", result.get("score", 0.0))
#     pct = int(max(0.0, min(1.0, semantic)) * 100)
#     if pct >= 70:
#         return f"🟢 {pct}%"
#     if pct >= 55:
#         return f"🟡 {pct}%"
#     return f"🔴 {pct}%"


def _render_status_sidebar(status: dict):
    """Show Ollama + model availability in the sidebar."""
    with st.sidebar:
        st.subheader("Model status")
        if not status["ollama_running"]:
            st.error(f"❌ Ollama not running — {status.get('error','')}")
            st.caption("Start Ollama:  `ollama serve`")
            return

        st.success("✅ Ollama running")

        if status["text_model_available"]:
            st.success(f"✅ Text: `{status['text_model']}`")
        else:
            st.warning(f"⚠️ Text model missing")
            st.caption(f"`ollama pull {status['text_model']}`")

        if status["vision_model_available"]:
            st.success(f"✅ Vision: `{status['vision_model']}`")
        else:
            st.warning(f"⚠️ Vision model missing")
            st.caption(f"`ollama pull {status['vision_model']}`")


# ── Report list ───────────────────────────────────────────────────────────────

def render_report_list(results: list[dict]):
    st.subheader("📄 Similar reports")
    st.caption(
        "Ranked by relevance — open each report to read the full resolution "
        "written by the team, including images and SQL."
    )
    for i, r in enumerate(results):
        # header = f"{_score_badge(r)}  **{r['title']}**  —  `{r['source']}`"
        header = f"  **{r['title']}**  —  `{r['source']}`"
        with st.expander(header, expanded=(i == 0)):
            st.markdown("**Most relevant excerpt:**")
            excerpt = r["text"]
            st.code(excerpt[:800] + ("…" if len(excerpt) > 800 else ""), language=None)

            path = r.get("path", "")
            if os.path.exists(path) and path.endswith(".json"):
                try:
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


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    st.set_page_config(page_title="Incident Chatbot", layout="wide")
    st.title("Incident Resolution Chatbot")
    st.caption("Describe your problem or upload a screenshot → resolution steps + matching reports")

    # Model status (sidebar)
    status = vlm_status()
    _render_status_sidebar(status)

    # Knowledge base
    try:
        embed_model, embeddings, documents, metadata, n_files = build_knowledge_base()
        st.sidebar.divider()
        st.sidebar.success(f"📚 {n_files} files · {len(documents)} chunks indexed")
    except Exception as e:
        st.sidebar.error(str(e))
        st.error(f"Knowledge base error — check your reports/ folder:\n{e}")
        st.stop()

    chat_tab, kb_tab, vlm_tab = st.tabs(["💬 Chat", "📚 Knowledge base", "🧪 VLM test"])

    # ── CHAT ─────────────────────────────────────────────────────────────────
    with chat_tab:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            user_text = st.text_area(
                "Describe the incident",
                height=160,
                placeholder="Paste the ticket description or any free-text description of what needs to be done…",
            )

        with col_right:
            vision_ok = status["ollama_running"] and status["vision_model_available"]
            upload_help = (
                "Any UI screenshot — the vision model reads it"
                if vision_ok
                else f"Vision model not available — pull it first: ollama pull {OLLAMA_VISION_MODEL}"
            )
            uploaded = st.file_uploader(
                "Screenshot (optional)",
                type=["png", "jpg", "jpeg", "webp"],
                help=upload_help,
            )
            if uploaded:
                st.image(Image.open(uploaded).convert("RGB"), use_column_width=True)

        go = st.button("Analyze & resolve", type="primary")

        if go:
            if not user_text.strip() and not uploaded:
                st.warning("Please enter a description or upload a screenshot.")
                st.stop()

            tmp_path = None
            text_query = ""
            image_query = ""
            image_analysis = NO_IMAGE_ANALYSIS

            with st.spinner("Understanding the problem…"):
                if user_text.strip():
                    text_query = understand_text(user_text.strip())

                if uploaded:
                    tmp_path = _tmp_write(uploaded)
                    try:
                        vlm_out = understand_screenshot(tmp_path)
                        if vlm_out.startswith("⚠️"):
                            st.warning(vlm_out)
                        else:
                            st.info(f"**Vision model read:** {vlm_out}")
                            image_query = vlm_out
                            image_analysis = vlm_out
                    except Exception as e:
                        st.warning(f"Vision model error ({e}) — using text only.")
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass

                if not text_query and not image_query:
                    st.error("Could not extract a problem description.")
                    st.stop()

                retrieval_problem = combine_retrieval_queries(text_query, image_query)

            with st.expander("🔍 Problem understood as", expanded=False):
                if text_query and image_query:
                    st.markdown("**From text:**")
                    st.write(text_query)
                    st.markdown("**From screenshot:**")
                    st.write(image_query)
                else:
                    st.write(retrieval_problem)

            with st.spinner("Searching knowledge base…"):
                results = search_multimodal(
                    text_query,
                    image_query,
                    embed_model,
                    embeddings,
                    documents,
                    metadata,
                    top_k=TOP_K,
                )

            if not results:
                st.warning("No documents in knowledge base. Add reports to the reports/ folder.")
                st.stop()

            top_score = results[0]["score"]

            st.divider()
            st.subheader("🔧 Resolution guide")

            with st.spinner("Generating resolution…"):
                if top_score < CONFIDENCE_THRESHOLD:
                    # st.warning(
                    #     f"Best match score is {int(top_score * 100)}% — below confidence threshold. "
                    #     "Showing general guidance only."
                    # )
                    prompt = format_prompt(
                        FALLBACK_PROMPT,
                        FALLBACK_PROMPT_REQUIRED,
                        problem=retrieval_problem,
                        image_analysis=image_analysis,
                    )
                else:
                    knowledge = format_retrieval_context(results, limit=3)
                    prompt = format_prompt(
                        RESOLUTION_PROMPT,
                        RESOLUTION_PROMPT_REQUIRED,
                        problem=retrieval_problem,
                        image_analysis=image_analysis,
                        knowledge=knowledge,
                    )

                raw = ask_ollama(prompt)
                parsed = parse_resolution(raw)
                render_guided_steps(parsed)

            st.divider()
            render_report_list(results)

    # ── KNOWLEDGE BASE ────────────────────────────────────────────────────────
    with kb_tab:
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
                with st.expander(f" {h['title']} — `{h['source']}`"):
                    st.text(h["text"][:500])

    # ── VLM TEST ──────────────────────────────────────────────────────────────
    with vlm_tab:
        if not status["ollama_running"]:
            st.error("Ollama is not running. Start it with:  `ollama serve`")
        elif not status["vision_model_available"]:
            st.warning(
                f"Vision model `{OLLAMA_VISION_MODEL}` is not pulled yet.\n\n"
                f"Run this once:  `ollama pull {OLLAMA_VISION_MODEL}`"
            )
        else:
            st.success(f"Vision model `{OLLAMA_VISION_MODEL}` is ready.")

        st.info("Raw vision model sandbox — test any prompt against any image.")
        vlm_prompt = st.text_area("Prompt", value=VLM_UNDERSTAND_PROMPT, height=140)
        max_tok = st.slider("Max tokens", 64, 512, 256, 32)
        up = st.file_uploader("Image", type=["png", "jpg", "jpeg", "webp"], key="vlm_img")

        c1, c2 = st.columns(2)
        run_up    = c1.button("Run on image", disabled=up is None)
        run_smoke = c2.button("Smoke test")

        img_path = None
        if up:
            st.image(Image.open(up).convert("RGB"), use_column_width=True)
            img_path = _tmp_write(up)

        if run_smoke:
            smoke = Image.new("RGB", (640, 320), "#f0f4f8")
            d = ImageDraw.Draw(smoke)
            d.rounded_rectangle(
                (30, 30, 610, 290), radius=20, fill="#dbe9f9", outline="#2c3e50", width=3
            )
            d.text((60, 260), "VLM smoke test image", fill="#1f2937")
            img_path = _tmp_save(smoke)
            st.image(smoke, use_column_width=True)

        if (run_up or run_smoke) and img_path:
            try:
                with st.spinner(f"Running {OLLAMA_VISION_MODEL}…"):
                    out = run_vlm(vlm_prompt, image_path=img_path, max_tokens=max_tok)
                st.subheader("Output")
                st.write(out)
            except Exception as e:
                st.error(f"VLM error: {e}")
            finally:
                if img_path and os.path.exists(img_path):
                    try:
                        os.unlink(img_path)
                    except OSError:
                        pass


def main():
    run()