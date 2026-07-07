"""
chatbot/llm.py — prompt helpers that turn raw input into LLM calls.

Ported from incident_chatbot/llm.py. Streamlit is gone, and the direct `ollama`
calls are replaced by calls through an injected LLMProvider, so the chatbot no
longer hard-depends on Ollama — the provider is swappable (Ollama today, Gemini
possible) per the architecture decision.

These are thin functions: build the prompt, call provider.chat / provider.vision.
"""

from __future__ import annotations

from app.shared.llm.provider import LLMProvider

from .prompts import (
    UNDERSTAND_PROMPT,
    UNDERSTAND_PROMPT_REQUIRED,
    VLM_UNDERSTAND_PROMPT,
    format_prompt,
)


def understand_text(text: str, provider: LLMProvider) -> str:
    """Summarize incident text into a retrieval query."""
    return provider.chat(
        format_prompt(
            UNDERSTAND_PROMPT,
            UNDERSTAND_PROMPT_REQUIRED,
            text=text.strip(),
        )
    )


def understand_screenshot(image_b64: str, provider: LLMProvider) -> str:
    """Extract a plain-text problem description from a screenshot (base64)."""
    return provider.vision(VLM_UNDERSTAND_PROMPT, image_b64)
