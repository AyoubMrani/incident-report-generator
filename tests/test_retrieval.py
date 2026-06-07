import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from incident_chatbot.retrieval import (
    _fuse_query_scores,
    _lexical_boost,
    combine_retrieval_queries,
    search,
    search_multimodal,
)


class _FakeEmbedder:
    def encode(self, texts, convert_to_numpy=True):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "defective" in lowered or "dashboard" in lowered:
                vectors.append(np.array([1.0, 0.0], dtype="float32"))
            elif "duplicate" in lowered or "yellow" in lowered:
                vectors.append(np.array([0.0, 1.0], dtype="float32"))
            else:
                vectors.append(np.array([0.5, 0.5], dtype="float32"))
        return np.stack(vectors)


def _fixture_corpus():
    documents = [
        "Defective port cleanup for homes still showing D status on dashboard.",
        "Duplicate record cleanup using support_remove_opv_duplicate for yellow rows.",
        "Home status change from HomePlanningPending to deployed.",
    ]
    metadata = [
        {
            "source": "reports/a.md",
            "path": "reports/a.md",
            "title": "Remove Defective Port Status",
            "chunk_id": 0,
            "incident_id": "INC0001",
        },
        {
            "source": "reports/b.md",
            "path": "reports/b.md",
            "title": "Duplicate OPV Cleanup",
            "chunk_id": 0,
            "incident_id": "INC0002",
        },
        {
            "source": "reports/c.md",
            "path": "reports/c.md",
            "title": "Home Status Change",
            "chunk_id": 0,
            "incident_id": "INC0003",
        },
    ]
    model = _FakeEmbedder()
    embeddings = model.encode(documents)
    return model, embeddings, documents, metadata


def test_combine_retrieval_queries_joins_text_and_image():
    combined = combine_retrieval_queries("text summary", "screenshot summary")
    assert "text summary" in combined
    assert "screenshot summary" in combined


def test_lexical_boost_prefers_matching_operational_phrases():
    boost = _lexical_boost(
        ["dashboard still marks homes as problematic after technician repair"],
        "Remove defective port D status from fm_opv",
        {"title": "Remove Defective Port Status", "incident_id": "INC0001"},
    )
    assert boost > 0


def test_search_multimodal_text_only():
    model, embeddings, documents, metadata = _fixture_corpus()
    results = search_multimodal(
        "technician repaired issue but dashboard still problematic",
        None,
        model,
        embeddings,
        documents,
        metadata,
        top_k=2,
    )
    assert results
    assert "Defective" in results[0]["title"]


def test_search_multimodal_image_query_can_shift_best_match():
    model, embeddings, documents, metadata = _fixture_corpus()
    results = search_multimodal(
        "customer impact is gone",
        "spreadsheet highlights yellow duplicate rows to delete",
        model,
        embeddings,
        documents,
        metadata,
        top_k=2,
    )
    assert results
    assert "Duplicate" in results[0]["title"]


def test_fuse_query_scores_blends_text_and_image():
    model, embeddings, documents, _ = _fixture_corpus()
    fused = _fuse_query_scores(
        "dashboard problematic homes",
        "yellow duplicate spreadsheet rows",
        model,
        embeddings,
    )
    text_only = _fuse_query_scores("dashboard problematic homes", None, model, embeddings)
    image_only = _fuse_query_scores(None, "yellow duplicate spreadsheet rows", model, embeddings)

    assert not np.allclose(fused, text_only)
    assert not np.allclose(fused, image_only)


def test_search_returns_semantic_and_lexical_components():
    model, embeddings, documents, metadata = _fixture_corpus()
    results = search(
        "defective port dashboard",
        model,
        embeddings,
        documents,
        metadata,
        top_k=1,
    )
    assert "semantic_score" in results[0]
    assert "lexical_boost" in results[0]
