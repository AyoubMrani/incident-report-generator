import os
from pathlib import Path

# ── Folders ───────────────────────────────────────────────────────────────────
REPORTS_FOLDER = "reports"
MODELS_FOLDER  = "models"

# ── Embedding ─────────────────────────────────────────────────────────────────
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE       = 700
CHUNK_OVERLAP    = 120

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K                  = 5
CONFIDENCE_THRESHOLD   = 0.50
RETRIEVAL_TEXT_WEIGHT  = 0.55
RETRIEVAL_IMAGE_WEIGHT = 0.45
LEXICAL_BOOST_MAX      = 0.12

# ── Ollama — text ─────────────────────────────────────────────────────────────
OLLAMA_MODEL = "llama3:8b"

# ── Ollama — vision ───────────────────────────────────────────────────────────
# qwen2.5vl:7b  — best quality, needs ~6 GB VRAM / unified memory
# qwen2.5vl:3b  — lighter option, needs ~3 GB, good for low-RAM machines
# minicpm-v      — alternative if Qwen is too heavy
OLLAMA_VISION_MODEL = "qwen2.5vl:3b"