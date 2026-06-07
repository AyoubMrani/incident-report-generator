import re

import numpy as np

from .config import (
    LEXICAL_BOOST_MAX,
    RETRIEVAL_IMAGE_WEIGHT,
    RETRIEVAL_TEXT_WEIGHT,
    TOP_K,
)

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "how", "i", "if", "in", "is", "it", "its", "me", "my", "of", "on",
    "or", "our", "should", "that", "the", "their", "there", "these", "this",
    "to", "we", "what", "which", "with", "you", "your", "do", "does", "did",
    "need", "can", "could", "would", "please", "some", "any", "still",
    "after", "before", "already", "only", "want", "make", "remove", "update",
    "fix", "change", "move", "delete", "clean", "cleanup",
})

# Query phrase groups → report phrases that indicate the same NRI workflow.
_OPERATIONAL_PHRASE_LINKS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("repaired", "technician", "problematic", "dashboard"), ("defective port", "d status")),
    (("indicators", "traces", "remove"), ("provision", "defective port", "status")),
    (("imported twice", "twice"), ("duplicate",)),
    (("highlights", "spreadsheet", "deleting"), ("duplicate", "yellow")),
    (("planning", "pending", "deployment"), ("home status", "homeplanning", "homeunplanned")),
    (("downstream", "old value", "source platform"), ("coma", "sync")),
    (("reporting", "stale"), ("export", "cleanup")),
    (("identifier", "spreadsheet", "database export"), ("access number", "mismatch")),
)


def combine_retrieval_queries(text_query: str, image_query: str | None) -> str:
    """Merge separate text and image retrieval queries for resolution prompts."""
    parts = [q.strip() for q in (text_query, image_query or "") if q and q.strip()]
    return "\n\n".join(parts)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOPWORDS and len(token) > 2
    }


def _lexical_boost(queries: list[str], document: str, meta: dict) -> float:
    """Small additive boost for identifier overlap and NRI operational phrases."""
    if not queries:
        return 0.0

    hay = f"{meta.get('title', '')} {document}".lower()
    boost = 0.0

    for query in queries:
        if not query or not query.strip():
            continue
        q_lower = query.lower()

        incident_id = meta.get("incident_id")
        if incident_id:
            inc_match = re.search(r"INC\d+", query, re.IGNORECASE)
            if inc_match and inc_match.group().upper() == str(incident_id).upper():
                boost = max(boost, LEXICAL_BOOST_MAX)

        q_tokens = _tokenize(query)
        if q_tokens:
            doc_tokens = _tokenize(hay)
            overlap = len(q_tokens & doc_tokens) / len(q_tokens)
            boost = max(boost, min(LEXICAL_BOOST_MAX * 0.75, overlap * LEXICAL_BOOST_MAX))

        for phrase in (
            "defective port", "provision", "duplicate", "home status",
            "coma", "export", "access number", "fm_opv", "homeplanning",
        ):
            if phrase in q_lower and phrase in hay:
                boost = max(boost, LEXICAL_BOOST_MAX * 0.6)

        for query_terms, report_terms in _OPERATIONAL_PHRASE_LINKS:
            if any(term in q_lower for term in query_terms):
                if any(term in hay for term in report_terms):
                    boost = max(boost, LEXICAL_BOOST_MAX * 0.85)

    return min(boost, LEXICAL_BOOST_MAX)


def _embedding_scores(query: str, embed_model, embeddings: np.ndarray) -> np.ndarray:
    q = embed_model.encode([query], convert_to_numpy=True).astype("float32")[0]
    q_norm = q / (np.linalg.norm(q) + 1e-9)
    doc_norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9
    return (embeddings / doc_norms) @ q_norm


def _fuse_query_scores(
    text_query: str | None,
    image_query: str | None,
    embed_model,
    embeddings: np.ndarray,
    *,
    text_weight: float = RETRIEVAL_TEXT_WEIGHT,
    image_weight: float = RETRIEVAL_IMAGE_WEIGHT,
) -> np.ndarray:
    text_query = (text_query or "").strip()
    image_query = (image_query or "").strip()

    if text_query and image_query:
        text_scores = _embedding_scores(text_query, embed_model, embeddings)
        image_scores = _embedding_scores(image_query, embed_model, embeddings)
        total = text_weight + image_weight
        return (text_weight / total) * text_scores + (image_weight / total) * image_scores
    if text_query:
        return _embedding_scores(text_query, embed_model, embeddings)
    if image_query:
        return _embedding_scores(image_query, embed_model, embeddings)
    return np.zeros(len(embeddings), dtype="float32")


def _best_chunk_per_source(
    scores: np.ndarray,
    documents: list[str],
    metadata: list[dict],
    queries: list[str],
) -> list[dict]:
    best_by_source: dict[str, dict] = {}

    for idx, semantic_score in enumerate(scores):
        meta = metadata[idx]
        source = meta["source"]
        lexical = _lexical_boost(queries, documents[idx], meta)
        combined = float(semantic_score) + lexical

        entry = {
            "text": documents[idx],
            "source": source,
            "path": meta["path"],
            "title": meta["title"],
            "chunk_id": meta["chunk_id"],
            "incident_id": meta.get("incident_id"),
            "score": combined,
            "semantic_score": float(semantic_score),
            "lexical_boost": lexical,
        }

        current = best_by_source.get(source)
        if current is None or combined > current["score"]:
            best_by_source[source] = entry

    return sorted(best_by_source.values(), key=lambda item: item["score"], reverse=True)


def search(
    query,
    embed_model,
    embeddings,
    documents,
    metadata,
    top_k: int = TOP_K,
    *,
    secondary_query: str | None = None,
    text_weight: float = RETRIEVAL_TEXT_WEIGHT,
    image_weight: float = RETRIEVAL_IMAGE_WEIGHT,
):
    """
    Hybrid retrieval over chunked reports.

    When ``secondary_query`` is set, semantic scores are a weighted blend of the
    primary (text) and secondary (image) embeddings. Lexical boosts are computed
    from both queries. One best-scoring chunk is returned per source file.
    """
    primary = (query or "").strip()
    secondary = (secondary_query or "").strip()

    if not primary and not secondary:
        return []

    scores = _fuse_query_scores(
        primary,
        secondary or None,
        embed_model,
        embeddings,
        text_weight=text_weight,
        image_weight=image_weight,
    )

    queries = [q for q in (primary, secondary) if q]
    ranked = _best_chunk_per_source(scores, documents, metadata, queries)
    return ranked[:top_k]


def search_multimodal(
    text_query: str | None,
    image_query: str | None,
    embed_model,
    embeddings,
    documents,
    metadata,
    top_k: int = TOP_K,
):
    """Convenience wrapper for text-only, image-only, and text+image retrieval."""
    text_query = (text_query or "").strip()
    image_query = (image_query or "").strip()

    if text_query and image_query:
        return search(
            text_query,
            embed_model,
            embeddings,
            documents,
            metadata,
            top_k=top_k,
            secondary_query=image_query,
        )
    if text_query:
        return search(text_query, embed_model, embeddings, documents, metadata, top_k=top_k)
    if image_query:
        return search(image_query, embed_model, embeddings, documents, metadata, top_k=top_k)
    return []
