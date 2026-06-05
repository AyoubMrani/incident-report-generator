"""
llm.py — LLM and VLM wrappers

  - Ollama (llama3:8b)     — text understanding + resolution generation
  - Qwen2.5-VL via MLX    — screenshot understanding (expected on dev machines)

Call vlm_status() before telling anyone to install mlx-vlm or that vision is "off".
"""

import importlib.util
import os

import streamlit as st

from incident_chatbot.config  import OLLAMA_MODEL, QWEN_MLX_PATH
from incident_chatbot.prompts import UNDERSTAND_PROMPT, VLM_UNDERSTAND_PROMPT


class VLMUnavailableError(RuntimeError):
    """Raised when screenshot analysis cannot run after a real attempt."""

    def __init__(self, reason: str, hint: str = "", *, package_installed: bool = False):
        self.reason = reason
        self.hint = hint
        self.package_installed = package_installed
        message = reason if not hint else f"{reason}. {hint}"
        super().__init__(message)


# ── Ollama ────────────────────────────────────────────────────────────────────

def ask_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    try:
        import ollama
        r = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return r["message"]["content"]
    except Exception as e:
        return f"⚠️ Ollama unavailable: {e}"


def understand_text(text: str) -> str:
    """Summarize incident text into a retrieval query."""
    return ask_ollama(UNDERSTAND_PROMPT.format(text=text.strip()))


# ── VLM (Qwen2.5-VL via MLX) ─────────────────────────────────────────────────

def vlm_status() -> dict:
    """
    Inspect vision stack without guessing.

    Returns:
        package_installed — importlib found mlx_vlm
        weights_present   — local MLX weights directory exists
        ready             — both true; safe to run vision inference
    """
    package_installed = importlib.util.find_spec("mlx_vlm") is not None
    model_path = os.path.expanduser(QWEN_MLX_PATH)
    weights_present = os.path.isdir(model_path)
    ready = package_installed and weights_present

    reason = ""
    hint = ""
    if not package_installed:
        reason = "mlx_vlm is not importable in this Python environment"
        hint = "pip install mlx-vlm"
    elif not weights_present:
        reason = f"MLX vision weights not found at {model_path}"
        hint = f"Place converted Qwen2.5-VL weights there or update QWEN_MLX_PATH in config.py"

    return {
        "package_installed": package_installed,
        "weights_present": weights_present,
        "ready": ready,
        "model_path": model_path,
        "reason": reason,
        "hint": hint,
    }


def vlm_availability() -> dict:
    """Backward-compatible wrapper around vlm_status()."""
    status = vlm_status()
    return {
        "available": status["ready"],
        "package_installed": status["package_installed"],
        "weights_present": status["weights_present"],
        "reason": status["reason"],
        "hint": status["hint"],
        "model_path": status["model_path"],
    }


@st.cache_resource(show_spinner=False)
def _load_vlm():
    from mlx_vlm import load

    resolved = os.path.expanduser(QWEN_MLX_PATH)
    if not os.path.isdir(resolved):
        raise ValueError(f"MLX model not found at {resolved}")

    model, processor = load(resolved)
    if getattr(processor, "chat_template", None) is None and hasattr(processor, "tokenizer"):
        processor.chat_template = getattr(processor.tokenizer, "chat_template", None)
    return model, processor


def run_vlm(prompt: str, image_path: str | None = None, max_tokens: int = 256) -> str:
    """Run Qwen2.5-VL. Raises VLMUnavailableError only after verified preconditions fail."""
    status = vlm_status()

    if not status["package_installed"]:
        raise VLMUnavailableError(
            status["reason"],
            status["hint"],
            package_installed=False,
        )

    if not status["weights_present"]:
        raise VLMUnavailableError(
            status["reason"],
            status["hint"],
            package_installed=True,
        )

    from mlx_vlm import generate, apply_chat_template

    try:
        model, processor = _load_vlm()
    except Exception as exc:
        raise VLMUnavailableError(
            f"Failed to load vision model: {exc}",
            status["hint"],
            package_installed=True,
        ) from exc

    if image_path:
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image_path},
            {"type": "text",  "text": prompt},
        ]}]
        pt = apply_chat_template(
            processor, model.config, messages,
            add_generation_prompt=True, num_images=1,
        )
        result = generate(
            model, processor, pt,
            image=[image_path], verbose=False, max_tokens=max_tokens,
        )
    else:
        pt = apply_chat_template(
            processor, model.config, prompt,
            add_generation_prompt=True, num_images=0,
        )
        result = generate(model, processor, pt, verbose=False, max_tokens=max_tokens)

    return getattr(result, "text", str(result)).strip()


def understand_screenshot(image_path: str) -> str:
    """Extract incident context from a screenshot for retrieval."""
    return run_vlm(VLM_UNDERSTAND_PROMPT, image_path=image_path, max_tokens=200)
