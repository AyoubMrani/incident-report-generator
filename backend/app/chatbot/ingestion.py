"""
chatbot/ingestion.py — build the retrieval knowledge base from report files.

Ported from the original incident_chatbot/ingestion.py with two changes needed
to run headless under FastAPI:

  1. Streamlit removed. The `@st.cache_resource` decorator on
     build_knowledge_base is gone — caching now happens by building the KB once
     in the app lifespan and holding it on app.state (see main.py). `st.warning`
     on an unindexable file becomes a collected warning on the returned object.

  2. The reports directory is a parameter, not the hard-coded REPORTS_FOLDER, so
     the chatbot indexes the same shared reports/ dir the generator writes to.

The file readers, chunking, title extraction, and INC-id extraction are
unchanged.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .config import CHUNK_OVERLAP, CHUNK_SIZE, EMBED_MODEL_NAME


@dataclass
class KnowledgeBase:
    """Everything retrieval.search() needs, built once and reused per process."""

    embed_model: object
    embeddings: np.ndarray
    documents: list[str]
    metadata: list[dict]
    n_files: int
    warnings: list[str] = field(default_factory=list)


# ── File readers (unchanged) ──────────────────────────────────────────────────


def _read_docx(path: str) -> str:
    # Lazy import: python-docx is only needed when a .docx report is indexed.
    from docx import Document

    doc = Document(path)
    parts = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(
                cell.text.strip() for cell in row.cells if cell.text.strip()
            )
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def _strip_html(text: str) -> str:
    """Quill stores paragraph content as HTML; reduce it to readable text."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def _render_block(block: dict) -> str:
    """Turn one report block into clean, human-readable text.

    This is the accuracy fix: the previous flattener emitted structural noise
    ('id: b4', 'type: heading', 'level: 2', base64 image blobs) that polluted
    embeddings and the LLM context. Here we extract only the incident *content*
    per block type, so retrieval matches on meaning and the model sees real text.
    """
    btype = block.get("type")
    title = (block.get("title") or "").strip()
    out: list[str] = []

    if btype == "heading":
        out.append(f"## {block.get('content', '').strip()}")
    elif btype == "paragraph":
        if title:
            out.append(f"{title}:")
        out.append(_strip_html(block.get("content", "")))
    elif btype == "list":
        if title:
            out.append(f"{title}:")
        if block.get("label"):
            out.append(str(block["label"]).strip())
        for item in block.get("items", []):
            out.append(f"- {_strip_html(str(item))}")
    elif btype == "code":
        # A code block may hold snippets and descriptions (see report schema).
        if title:
            out.append(f"{title}:")
        for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
            if isinstance(item, dict):
                if item.get("header"):
                    out.append(str(item["header"]).strip())
                if item.get("content"):
                    out.append(str(item["content"]).strip())
        # Some code blocks store content directly.
        if block.get("content"):
            out.append(str(block["content"]).strip())
    elif btype == "table":
        if title:
            out.append(f"{title}:")
        headers = block.get("headers", [])
        if headers:
            out.append(" | ".join(str(h) for h in headers))
        for row in block.get("rows", []):
            out.append(" | ".join(str(c) for c in row))
    elif btype in ("incident_example",):
        ref = block.get("incident_id", "")
        link = block.get("link", "")
        out.append(f"Related incident: {ref} {link}".strip())
    elif btype in ("description_box",):
        if title:
            out.append(f"{title}:")
        out.append(_strip_html(block.get("content", "")))
    elif btype == "image":
        # Skip the base64 data_url; keep only a human caption if present.
        cap = (block.get("caption") or "").strip()
        if cap:
            out.append(f"[image: {cap}]")

    return "\n".join(p for p in out if p)


def _read_json(path: str) -> str:
    """Extract clean incident text from a report JSON (schema-aware).

    Handles both on-disk shapes: flat {metadata, blocks} and the legacy wrapper
    {report: {metadata, blocks}}. Emits title, key metadata, and the readable
    content of each block — no structural keys, no base64.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Unwrap the legacy {editingFilename, markdown, report:{...}} shape.
    report = data.get("report") if isinstance(data.get("report"), dict) else data
    metadata = report.get("metadata", {}) if isinstance(report, dict) else {}
    blocks = report.get("blocks", []) if isinstance(report, dict) else []

    lines: list[str] = []
    # Lead with the identifying metadata so it's searchable and grounds the model.
    if metadata.get("title"):
        lines.append(f"# {metadata['title']}")
    for key in ("incident_id", "category", "subcategory", "caller", "date", "priority"):
        if metadata.get(key):
            lines.append(f"{key}: {metadata[key]}")

    for block in blocks:
        if isinstance(block, dict):
            rendered = _render_block(block)
            if rendered:
                lines.append(rendered)

    # Fallback: if this wasn't a report-shaped JSON at all, keep the markdown.
    if not blocks and isinstance(data.get("markdown"), str):
        lines.append(data["markdown"])

    return "\n".join(lines)


def _read_md(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def _get_report_title(path: str, content: str) -> str:
    filename = os.path.splitext(os.path.basename(path))[0]
    if path.endswith(".json"):
        try:
            data = json.loads(content)
            metadata = data.get("metadata", {})
            title = metadata.get("title") or metadata.get("incident_id")
            if title:
                return str(title)
        except Exception:
            pass
    if path.endswith(".md"):
        for line in content.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
    match = re.search(r"INC\d+", content, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return filename


def _extract_incident_id_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"INC\d+", str(text), re.IGNORECASE)
    return match.group(0).upper() if match else None


# ── Knowledge base builder (Streamlit removed) ────────────────────────────────


def build_knowledge_base(reports_dir: str | Path) -> KnowledgeBase:
    """Index every supported file under ``reports_dir`` into a KnowledgeBase.

    Raises ValueError if the directory is missing or yields no indexable
    documents (same failure conditions as the original).
    """
    from sentence_transformers import SentenceTransformer

    reports_dir = str(reports_dir)

    loaders: dict[str, Callable[[str], str]] = {
        ".docx": _read_docx,
        ".json": _read_json,
        ".md": _read_md,
        ".txt": _read_md,
    }

    if not os.path.isdir(reports_dir):
        raise ValueError(
            f"Reports directory not found: {os.path.abspath(reports_dir)}. "
            "Create it and add incident documents."
        )

    documents: list[str] = []
    metadata: list[dict] = []
    warnings: list[str] = []
    n_files = 0

    root_label = os.path.basename(os.path.normpath(reports_dir))
    for filename in sorted(os.listdir(reports_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in loaders:
            continue
        path = os.path.join(reports_dir, filename)
        source = f"{root_label}/{filename}"
        try:
            content = loaders[ext](path)
            title = _get_report_title(path, content)
            incident_id = _extract_incident_id_from_text(content)
            for chunk_id, chunk in enumerate(_chunk(content)):
                documents.append(chunk)
                metadata.append(
                    {
                        "source": source,
                        "path": path,
                        "title": title,
                        "chunk_id": chunk_id,
                        "incident_id": incident_id,
                    }
                )
            n_files += 1
        except Exception as exc:  # noqa: BLE001 — keep indexing other files
            warnings.append(f"Could not index {source}: {exc}")

    if not documents:
        raise ValueError(
            "Knowledge base is empty — add .docx / .json / .md files to the "
            f"reports directory ({os.path.abspath(reports_dir)})."
        )

    model = SentenceTransformer(EMBED_MODEL_NAME)
    embeddings = (
        model.encode(documents, convert_to_numpy=True, show_progress_bar=False)
        .astype("float32")
    )
    return KnowledgeBase(
        embed_model=model,
        embeddings=embeddings,
        documents=documents,
        metadata=metadata,
        n_files=n_files,
        warnings=warnings,
    )
