"""
chatbot/config.py — chatbot tuning constants.

Ported verbatim from the original Chatbot project (incident_chatbot/config.py),
minus the folder constants: the reports directory is now injected by the app
(see main.py / ChatbotService) rather than hard-coded, so the chatbot and the
report generator share one directory.
"""

# ── Embedding ─────────────────────────────────────────────────────────────────
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE = 700
CHUNK_OVERLAP = 120

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K = 5                    # hits retrieved (all shown as sources/citations)
RESOLUTION_CONTEXT_K = 3     # top hits actually fed into the LLM prompt (latency)
# Cap the resolution generation. This must be large enough for a full answer:
# a documented procedure can carry several steps plus a verbatim multi-line
# query, and a cap that truncates the JSON mid-string loses the entire answer.
MAX_ANSWER_TOKENS = 2000
CONFIDENCE_THRESHOLD = 0.50
RETRIEVAL_TEXT_WEIGHT = 0.55
RETRIEVAL_IMAGE_WEIGHT = 0.45
LEXICAL_BOOST_MAX = 0.12

# ── Ollama — text ─────────────────────────────────────────────────────────────
# llama3.2:3b measured ~2x faster than llama3:8b on M4 (46 vs 17 tok/s) with
# equal-or-better answer quality on clean retrieval context — the better local
# tradeoff. Override with the OLLAMA_MODEL env var if you prefer 8b.
import os as _os

OLLAMA_MODEL = _os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# ── Ollama — vision ───────────────────────────────────────────────────────────
# qwen2.5vl:7b  — best quality, needs ~6 GB VRAM / unified memory
# qwen2.5vl:3b  — lighter option, needs ~3 GB, good for low-RAM machines
# minicpm-v      — alternative if Qwen is too heavy
OLLAMA_VISION_MODEL = "qwen2.5vl:3b"


# ── Answer cache ──────────────────────────────────────────────────────────────
# Repeat questions are common in an incident desk (a shift asks the same thing
# the previous shift did). Caching the shaped answer per prompt turns a ~15s
# local generation into an instant reply. Keyed on the full prompt, so new
# evidence or a new correction never serves a stale answer. 0 disables it.
ANSWER_CACHE_SIZE = int(_os.environ.get("ANSWER_CACHE_SIZE", "128"))
