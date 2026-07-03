"""
shared/llm/gemini_provider.py — Google Gemini implementation of LLMProvider.

The report generator originally called Gemini from the browser (via
@google/genai, key exposed through Vite `define`). Moving those calls behind
this server-side provider is what lets the API key stay off the client. The
report-generation feature can call `chat()` here in a later phase.

`import google.genai` is done lazily so the backend boots without the SDK or an
API key when only the Ollama-backed chatbot is in use (the current local setup).
"""

from __future__ import annotations

import os

from app.shared.llm.provider import LLMProvider

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model

    def _client(self):
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set; cannot use the Gemini provider."
            )
        from google import genai  # lazy import

        return genai.Client(api_key=self.api_key)

    def chat(self, prompt: str, *, model: str | None = None) -> str:
        client = self._client()
        response = client.models.generate_content(
            model=model or self.model,
            contents=prompt,
        )
        return response.text or ""

    def vision(
        self,
        prompt: str,
        image_b64: str,
        *,
        model: str | None = None,
    ) -> str:
        client = self._client()
        from google.genai import types  # lazy import

        image_part = types.Part.from_bytes(
            data=__import__("base64").b64decode(image_b64),
            mime_type="image/png",
        )
        response = client.models.generate_content(
            model=model or self.model,
            contents=[prompt, image_part],
        )
        return response.text or ""
