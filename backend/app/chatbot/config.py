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
# Cap the resolution generation. This must be large enough for a full answer:
# a documented procedure can carry several steps plus a verbatim multi-line
# query, and a cap that truncates the JSON mid-string loses the entire answer.
MAX_ANSWER_TOKENS = 2000
CONFIDENCE_THRESHOLD = 0.50
RETRIEVAL_TEXT_WEIGHT = 0.55
RETRIEVAL_IMAGE_WEIGHT = 0.45
LEXICAL_BOOST_MAX = 0.12

# ── Ollama — text ─────────────────────────────────────────────────────────────
# Measured on the corpus, not on a handful of chosen queries. Both models ran
# eval/corpus_sweep.py --answers over the same 15 sampled reports (same --seed,
# identical pipeline, only the model varied; M4 / 17 GB):
#
#   model         reports   checks   mean conf   mean steps   median latency
#   llama3.2:3b    15/15     60/60      88.7%        4.0           28.1s
#   llama3:8b      15/15     60/60      92.0%        3.4           40.3s
#
# Correctness is a tie on every property that matters: both answer all 15
# reports, both pass all 60 checks. 8b reports more confidence *in itself*
# while producing *fewer* resolution steps — on two reports it returned a
# single step where 3b returned three or four — and takes 43% longer. That is
# the signature of retrieval and grounding doing the work rather than model
# size, which is what the tie in correctness says directly.
#
# So 3b is not a compromise here; it is the better answer on this corpus. On an
# incident desk a 28s answer that gets used also beats a 40s answer that gets
# abandoned.
#
# Switch without a rebuild:  OLLAMA_MODEL=llama3:8b docker compose up -d
# Reproduce:  python eval/corpus_sweep.py --answers --limit 15 --model <name>
#             python eval/compare_sweeps.py eval/sweep_llama3.2-3b.json \
#                 eval/sweep_llama3-8b.json --labels llama3.2:3b llama3:8b
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
