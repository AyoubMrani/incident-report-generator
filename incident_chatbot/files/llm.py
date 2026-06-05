"""
llm.py — LLM and VLM wrappers

Two models:
  - Ollama (llama3:8b)      — text understanding + resolution generation
  - Qwen2.5-VL via MLX     — screenshot understanding (optional, Apple Silicon)

Both return plain strings. Callers decide what to do with the output.
"""

import os
import streamlit as st

from incident_chatbot.config  import OLLAMA_MODEL, QWEN_MLX_PATH
from incident_chatbot.prompts import UNDERSTAND_PROMPT, VLM_UNDERSTAND_PROMPT


# ── Ollama ────────────────────────────────────────────────────────────────────

def ask_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    try:
        import ollama
        r = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return r["message"]["content"]
    except Exception as e:
        return f"⚠️ Ollama unavailable: {e}"


def understand_text(text: str) -> str:
    """Summarize a text incident into a clean search query."""
    return ask_ollama(UNDERSTAND_PROMPT.format(text=text.strip()))


# ── VLM (Qwen2.5-VL via MLX) ─────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _load_vlm():
    from mlx_vlm import load
    resolved = os.path.expanduser(QWEN_MLX_PATH)
    if not os.path.isdir(resolved):
        raise ValueError(
            f"MLX model not found at {resolved}. "
            "Run: mlx_lm.convert --hf-path Qwen/Qwen2.5-VL-7B-Instruct "
            "--mlx-path ./models/qwen2.5-vl-7b-4bit-vlm -q"
        )
    model, processor = load(resolved)
    # Patch missing chat_template (some MLX exports omit it)
    if getattr(processor, "chat_template", None) is None and hasattr(processor, "tokenizer"):
        processor.chat_template = getattr(processor.tokenizer, "chat_template", None)
    return model, processor


def run_vlm(prompt: str, image_path: str | None = None, max_tokens: int = 256) -> str:
    """Run Qwen2.5-VL on an image + prompt. Falls back to Ollama if VLM unavailable."""
    try:
        from mlx_vlm import generate, apply_chat_template
        model, processor = _load_vlm()

        if image_path:
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image_path},
                {"type": "text",  "text": prompt},
            ]}]
            pt = apply_chat_template(
                processor, model.config, messages,
                add_generation_prompt=True, num_images=1,
            )
            result = generate(model, processor, pt,
                              image=[image_path], verbose=False, max_tokens=max_tokens)
        else:
            pt = apply_chat_template(
                processor, model.config, prompt,
                add_generation_prompt=True, num_images=0,
            )
            result = generate(model, processor, pt, verbose=False, max_tokens=max_tokens)

        return getattr(result, "text", str(result)).strip()

    except Exception as e:
        # Graceful fallback: describe the failure, don't crash
        return f"VLM unavailable ({e}). Upload a text description instead."


def understand_screenshot(image_path: str) -> str:
    """Extract a plain-text problem description from a screenshot."""
    return run_vlm(VLM_UNDERSTAND_PROMPT, image_path=image_path, max_tokens=200)
