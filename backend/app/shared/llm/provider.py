"""
shared/llm/provider.py — the swappable LLM abstraction.

The unified app must support two providers side by side (per the architecture
decision): the chatbot runs on self-hosted Ollama, the generator uses Gemini.
Both modules depend on this interface, never on `ollama` or `@google/genai`
directly, so a provider can be swapped by config without touching call sites.

Phase 2 fills in the concrete implementations:
  - OllamaProvider  — wraps the chatbot's existing ask_ollama / run_vlm
  - GeminiProvider  — moves the generator's Gemini calls server-side

This file defines only the contract so the rest of the backend can be written
against it now.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMUnavailable(Exception):
    """The model backend could not be reached / failed to run.

    Distinct from "the model ran and returned text" so the pipeline can surface
    a clear error to the user instead of a fabricated low-confidence answer.
    """


class LLMProvider(ABC):
    """Provider-agnostic text + vision chat surface."""

    @abstractmethod
    def chat(self, prompt: str, *, model: str | None = None) -> str:
        """Return the model's text completion for a single-turn prompt."""

    @abstractmethod
    def vision(
        self,
        prompt: str,
        image_b64: str,
        *,
        model: str | None = None,
    ) -> str:
        """Return the model's response for a prompt plus a base64 image.

        Providers without vision support should raise NotImplementedError.
        """

    def chat_stream(self, prompt: str, *, model: str | None = None) -> Iterator[str]:
        """Yield the completion in chunks as it is generated.

        Default implementation falls back to a single non-streamed chunk, so any
        provider works with the streaming endpoint even if it can't stream.
        Providers that support streaming (Ollama) override this.
        """
        yield self.chat(prompt, model=model)


def get_provider(name: str) -> LLMProvider:
    """Factory: resolve a provider by name (e.g. 'ollama', 'gemini').

    Imports are local so that, e.g., using the Ollama chatbot does not require
    the Gemini SDK to be installed, and vice versa.
    """
    key = name.lower().strip()
    if key == "ollama":
        from app.shared.llm.ollama_provider import OllamaProvider

        return OllamaProvider()
    if key == "gemini":
        from app.shared.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider: {name!r} (expected 'ollama' or 'gemini').")
