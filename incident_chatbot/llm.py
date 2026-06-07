import base64
import os
import sys
from pathlib import Path
 
import streamlit as st
 
from incident_chatbot.config import OLLAMA_MODEL, OLLAMA_VISION_MODEL
from incident_chatbot.prompts import (
    UNDERSTAND_PROMPT,
    UNDERSTAND_PROMPT_REQUIRED,
    VLM_UNDERSTAND_PROMPT,
    format_prompt,
)


# class VLMUnavailableError(RuntimeError):
#     """Raised when screenshot analysis cannot run after a real attempt."""

#     def __init__(self, reason: str, hint: str = "", *, package_installed: bool = False):
#         self.reason = reason
#         self.hint = hint
#         self.package_installed = package_installed
#         message = reason if not hint else f"{reason}. {hint}"
#         super().__init__(message)


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
    return ask_ollama(
        format_prompt(
            UNDERSTAND_PROMPT,
            UNDERSTAND_PROMPT_REQUIRED,
            text=text.strip(),
        )
    )

def _image_to_base64(image_path: str) -> str:
    """Read any image file and return a base64 string."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ── VLM (Qwen2.5-VL via MLX) ─────────────────────────────────────────────────

def vlm_status() -> dict:
    """
    Check whether Ollama and the vision model are available.
 
    Returns:
        {
            "ollama_running": bool,
            "vision_model_available": bool,
            "vision_model": str,
            "text_model_available": bool,
            "text_model": str,
            "error": str | None,
        }
    """
    result = {
        "ollama_running": False,
        "vision_model_available": False,
        "vision_model": OLLAMA_VISION_MODEL,
        "text_model_available": False,
        "text_model": OLLAMA_MODEL,
        "error": None,
    }
    try:
        import ollama
        models_response = ollama.list()
        pulled = {m["model"] for m in models_response.get("models", [])}
 
        # Normalize: Ollama stores tags like "qwen2.5vl:7b"
        def _is_pulled(name: str) -> bool:
            # exact match or name without tag
            return name in pulled or any(
                p == name or p.startswith(name + ":") or p.split(":")[0] == name.split(":")[0]
                for p in pulled
            )
 
        result["ollama_running"] = True
        result["vision_model_available"] = _is_pulled(OLLAMA_VISION_MODEL)
        result["text_model_available"] = _is_pulled(OLLAMA_MODEL)
 
    except Exception as e:
        result["error"] = str(e)
 
    return result



# def vlm_availability() -> dict:
#     """Backward-compatible wrapper around vlm_status()."""
#     status = vlm_status()
#     return {
#         "available": status["ready"],
#         "package_installed": status["package_installed"],
#         "weights_present": status["weights_present"],
#         "reason": status["reason"],
#         "hint": status["hint"],
#         "model_path": status["model_path"],
#     }


# @st.cache_resource(show_spinner=False)
# def _load_vlm():
#     from mlx_vlm import load

#     resolved = os.path.expanduser(QWEN_MLX_PATH)
#     if not os.path.isdir(resolved):
#         raise ValueError(f"MLX model not found at {resolved}")

#     model, processor = load(resolved)
#     if getattr(processor, "chat_template", None) is None and hasattr(processor, "tokenizer"):
#         processor.chat_template = getattr(processor.tokenizer, "chat_template", None)
#     return model, processor


def run_vlm(
    prompt: str,
    image_path: str | None = None,
    max_tokens: int = 256,
    model: str | None = None,
) -> str:
    """
    Run the vision model via Ollama.
 
    Works on macOS, Windows, and Linux — no MLX required.
    Falls back gracefully if the vision model is not pulled.
    """
    vision_model = model or OLLAMA_VISION_MODEL
    try:
        import ollama
 
        if image_path:
            b64 = _image_to_base64(image_path)
            response = ollama.chat(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64],
                    }
                ],
                options={"num_predict": max_tokens},
            )
        else:
            response = ollama.chat(
                model=vision_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": max_tokens},
            )
 
        return response["message"]["content"].strip()
 
    except ollama.ResponseError as e:
        if "model" in str(e).lower() and "not found" in str(e).lower():
            return (
                f"⚠️ Vision model '{vision_model}' is not installed in Ollama.\n"
                f"Run:  ollama pull {vision_model}"
            )
        return f"⚠️ Ollama vision error: {e}"
    except Exception as e:
        return f"⚠️ Vision model unavailable: {e}"
 
 
def understand_screenshot(image_path: str) -> str:
    """Extract a plain-text problem description from a screenshot."""
    return run_vlm(VLM_UNDERSTAND_PROMPT, image_path=image_path, max_tokens=200)
