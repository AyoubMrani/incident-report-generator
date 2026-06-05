"""
config.py — all configurable constants in one place.
Change values here; nothing else needs to be touched.
"""
import os

# ── Folders ───────────────────────────────────────────────────────────────────
REPORTS_FOLDER = "reports"          # where incident reports live (JSON + MD)
MODELS_FOLDER  = "models"           # local MLX model root

# ── Embedding ─────────────────────────────────────────────────────────────────
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE       = 700
CHUNK_OVERLAP    = 120

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K                = 5
CONFIDENCE_THRESHOLD = 0.50     # below this score → fallback prompt

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_MODEL = "llama3:8b"

# ── VLM ──────────────────────────────────────────────────────────────────────
QWEN_MLX_PATH = os.path.join(MODELS_FOLDER, "qwen2.5-vl-7b-4bit-vlm")
