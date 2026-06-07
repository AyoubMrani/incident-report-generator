"""
ui.py — Streamlit interface

Tabs:
  Chat       — main flow: input → understand → search → guided resolution + report list
  Knowledge  — inspect what is indexed (sidebar search)
  VLM Test   — raw vision model sandbox
"""

import os
import tempfile

import streamlit as st
from PIL import Image, ImageDraw

from incident_chatbot.config   import TOP_K, QWEN_MLX_PATH
from incident_chatbot.ingestion import build_knowledge_base
from incident_chatbot.retrieval import search
from incident_chatbot.llm       import understand_text, understand_screenshot, ask_ollama
from incident_chatbot.prompts   import (
    RESOLUTION_PROMPT,
    FALLBACK_PROMPT,
    VLM_UNDERSTAND_PROMPT,
    RESOLUTION_PROMPT_REQUIRED,
    FALLBACK_PROMPT_REQUIRED,
    NO_IMAGE_ANALYSIS,
    format_prompt,
)
from incident_chatbot.resolution import parse_resolution, render_guided_steps

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

# def _score_badge(score: float) -> str:
#     pct = int(score * 100)
#     if pct >= 80:
#         return f"🟢 {pct}%"
#     if pct >= 60:
#         return f"🟡 {pct}%"
#     return f"🔴 {pct}%"

CONFIDENCE_THRESHOLD = 0.50   # below this → fallback prompt

# ── Report list ───────────────────────────────────────────────────────────────

def render_report_list(results: list[dict]):
    st.subheader("📄 Similar reports")
    st.caption(
        "Ranked by relevance. Open each report to read the full resolution "
        "written by the team — including images and SQL."
    )

    for i, r in enumerate(results):
        # header = f"{_score_badge(r['score'])}  **{r['title']}**  —  `{r['source']}`"
        header = f"  **{r['title']}**  —  `{r['source']}`"
        with st.expander(header, expanded=(i == 0)):
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
    st.set_page_config(page_title="Incident Chatbot", layout="wide")
    st.title("Incident Resolution Chatbot")
    st.caption("Describe your problem or upload a screenshot → get resolution steps and matching reports")

    # Load knowledge base once
    try:
        embed_model, embeddings, documents, metadata, n_files = build_knowledge_base()
        st.sidebar.success(f"✅ {n_files} files · {len(documents)} chunks indexed")
    except Exception as e:
        st.sidebar.error(str(e))
        st.error(f"Knowledge base error — check your reports/ folder: {e}")
        st.stop()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    chat_tab, kb_tab, vlm_tab = st.tabs(["💬 Chat", "📚 Knowledge base", "🧪 VLM test"])

    # ── CHAT ─────────────────────────────────────────────────────────────────
    with chat_tab:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            user_text = st.text_area(
                "Describe the incident",
                height=160,
                placeholder=(
                    "Paste the ticket description, error message, or any free-text "
                    "description of what needs to be done…"
                ),
            )

        with col_right:
            uploaded = st.file_uploader(
                "Screenshot (optional)",
                type=["png", "jpg", "jpeg", "webp"],
                help="Any UI screenshot — the vision model reads it",
            )
            if uploaded:
                st.image(Image.open(uploaded).convert("RGB"), use_column_width=True)

        go = st.button("Analyze & resolve", type="primary")

        if go:
            if not user_text.strip() and not uploaded:
                st.warning("Please enter a description or upload a screenshot.")
                st.stop()

            tmp_path = None
            problem = ""
            image_analysis = NO_IMAGE_ANALYSIS

            # Step 1 — understand
            with st.spinner("Understanding the problem…"):
                if uploaded:
                    tmp_path = _tmp_write(uploaded)
                    try:
                        vlm_out = understand_screenshot(tmp_path)
                        if vlm_out.startswith("⚠️"):
                            st.warning(vlm_out)
                            problem = user_text.strip()
                        else:
                            st.info(f"**Vision model read:** {vlm_out}")
                            image_analysis = vlm_out
                            parts = [user_text.strip(), vlm_out]
                            problem = "\n\n".join(p for p in parts if p)
                    except Exception as e:
                        st.warning(f"Vision model unavailable ({e}) — using text only.")
                        problem = user_text.strip()
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                else:
                    problem = user_text.strip()

                if not problem:
                    st.error("Could not extract a problem description.")
                    st.stop()

                understood = understand_text(problem)

            with st.expander("🔍 Problem understood as:", expanded=False):
                st.write(understood)

            # Step 2 — search
            with st.spinner("Searching knowledge base…"):
                results = search(understood, embed_model, embeddings, documents, metadata, top_k=TOP_K)

            if not results:
                st.warning("No documents in knowledge base. Add reports to the reports/ folder.")
                st.stop()

            top_score = results[0]["score"]

            # Step 3 — resolution
            st.divider()
            st.subheader("🔧 Resolution guide")

            with st.spinner("Generating resolution…"):
                if top_score < CONFIDENCE_THRESHOLD:
                    st.warning(
                        f"Best match score is {int(top_score*100)}% — below confidence threshold. "
                        "Showing general guidance only."
                    )
                    prompt = format_prompt(
                        FALLBACK_PROMPT,
                        FALLBACK_PROMPT_REQUIRED,
                        problem=understood,
                        image_analysis=image_analysis,
                    )
                else:
                    knowledge = "\n\n---\n".join(
                        f"[{c['title']}]\n{c['text']}" for c in results[:3]
                    )
                    prompt = format_prompt(
                        RESOLUTION_PROMPT,
                        RESOLUTION_PROMPT_REQUIRED,
                        problem=understood,
                        image_analysis=image_analysis,
                        knowledge=knowledge,
                    )

                raw = ask_ollama(prompt)
                parsed = parse_resolution(raw)
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
                with st.expander(f" {h['title']} — `{h['source']}`"):
                    st.text(h["text"][:500])

    # ── VLM TEST ──────────────────────────────────────────────────────────────
    with vlm_tab:
        st.info("Raw vision model sandbox — test any prompt against any image.")

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
            except Exception as e:
                st.error(f"VLM error: {e}")
            finally:
                if img_path and os.path.exists(img_path):
                    os.unlink(img_path)
