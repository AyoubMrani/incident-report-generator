"""
shared/llm/ollama_provider.py — self-hosted Ollama implementation of LLMProvider.

Wraps the exact Ollama calls the original chatbot made in incident_chatbot/llm.py
(ollama.chat for text, ollama.chat with `images` for vision), behind the shared
interface so the chatbot no longer imports `ollama` directly.

Honours the OLLAMA_HOST env var (set in docker-compose) via the ollama client's
own host resolution; when unset it defaults to http://localhost:11434.
"""

from __future__ import annotations

import os
import time

from app.chatbot.config import MAX_ANSWER_TOKENS, OLLAMA_MODEL, OLLAMA_VISION_MODEL
from app.shared.llm.provider import LLMProvider, LLMUnavailable
from app.shared.logging import get_logger

log = get_logger("app.llm.ollama")

# Without a timeout a wedged model holds the worker thread for ever and the
# request never returns — the client just spins. Generation on a 3B model is
# tens of seconds, so the ceiling is generous; it exists to bound the pathological
# case, not to cut off normal work. Override with OLLAMA_TIMEOUT (seconds).
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        text_model: str = OLLAMA_MODEL,
        vision_model: str = OLLAMA_VISION_MODEL,
    ):
        self.text_model = text_model
        self.vision_model = vision_model

    # keep_alive holds the model in memory between requests so it doesn't cold-
    # reload each turn (a common cause of the ~30s+ spikes and intermittent
    # drops). format="json" constrains output to valid JSON — no "Here is the
    # resolution:" preamble to waste tokens, and far more reliable parsing.
    _KEEP_ALIVE = "30m"

    @staticmethod
    def _client():
        """An Ollama client with a bounded timeout.

        ollama.Client forwards kwargs to httpx, so `timeout` covers connect and
        read. Built per call: the object is cheap and this keeps the provider
        free of connection state across threads.
        """
        import ollama

        return ollama.Client(
            host=os.getenv("OLLAMA_HOST") or None,
            timeout=OLLAMA_TIMEOUT,
        )

    def chat(self, prompt: str, *, model: str | None = None) -> str:
        started = time.perf_counter()
        chosen = model or self.text_model
        try:
            response = self._client().chat(
                model=chosen,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                keep_alive=self._KEEP_ALIVE,
                options={"num_predict": MAX_ANSWER_TOKENS},
            )
            log.info("generation complete in %.1fs",
                     time.perf_counter() - started,
                     extra={"event": "llm_chat", "model": chosen,
                            "duration_ms": round((time.perf_counter() - started) * 1000)})
            return response["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            # Raise (don't return an error string) so the pipeline surfaces a
            # real error instead of parsing junk into a fake Unknown answer.
            log.error("generation failed after %.1fs: %s",
                      time.perf_counter() - started, exc,
                      extra={"event": "llm_chat_failed", "model": chosen})
            raise LLMUnavailable(str(exc)) from exc

    def chat_stream(self, prompt: str, *, model: str | None = None):
        """Yield content chunks as Ollama generates them."""
        started = time.perf_counter()
        chosen = model or self.text_model
        try:
            stream = self._client().chat(
                model=chosen,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                format="json",
                keep_alive=self._KEEP_ALIVE,
                options={"num_predict": MAX_ANSWER_TOKENS},
            )
            for chunk in stream:
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
            log.info("stream complete in %.1fs",
                     time.perf_counter() - started,
                     extra={"event": "llm_stream", "model": chosen,
                            "duration_ms": round((time.perf_counter() - started) * 1000)})
        except Exception as exc:  # noqa: BLE001
            log.error("stream failed after %.1fs: %s",
                      time.perf_counter() - started, exc,
                      extra={"event": "llm_stream_failed", "model": chosen})
            raise LLMUnavailable(str(exc)) from exc

    def vision(
        self,
        prompt: str,
        image_b64: str,
        *,
        model: str | None = None,
        max_tokens: int = 256,
    ) -> str:
        vision_model = model or self.vision_model
        try:
            response = self._client().chat(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_b64],
                    }
                ],
                options={"num_predict": max_tokens},
            )
            return response["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("vision call failed: %s", exc,
                        extra={"event": "llm_vision_failed", "model": vision_model})
            msg = str(exc).lower()
            if "not found" in msg and "model" in msg:
                return (
                    f"⚠️ Vision model '{vision_model}' is not installed in Ollama.\n"
                    f"Run:  ollama pull {vision_model}"
                )
            return f"⚠️ Vision model unavailable: {exc}"

    def status(self) -> dict:
        """Report Ollama reachability and whether the models are pulled.

        Ported from the original vlm_status() so the /api/health surface can
        expose chatbot readiness.
        """
        result = {
            "ollama_running": False,
            "text_model": self.text_model,
            "text_model_available": False,
            "vision_model": self.vision_model,
            "vision_model_available": False,
            "error": None,
        }
        try:
            pulled = {m["model"] for m in self._client().list().get("models", [])}

            def _is_pulled(name: str) -> bool:
                return name in pulled or any(
                    p == name
                    or p.startswith(name + ":")
                    or p.split(":")[0] == name.split(":")[0]
                    for p in pulled
                )

            result["ollama_running"] = True
            result["text_model_available"] = _is_pulled(self.text_model)
            result["vision_model_available"] = _is_pulled(self.vision_model)
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama status check failed: %s", exc,
                        extra={"event": "llm_status_failed"})
            result["error"] = str(exc)
        return result
