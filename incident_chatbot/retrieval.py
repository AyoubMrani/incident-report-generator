import numpy as np

from .config import TOP_K


def search(query, embed_model, embeddings, documents, metadata, top_k: int = TOP_K):
    q = embed_model.encode([query], convert_to_numpy=True).astype("float32")[0]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9
    scores = (embeddings / norms) @ (q / (np.linalg.norm(q) + 1e-9))
    top_idx = np.argsort(scores)[::-1]

    seen, results = set(), []
    for idx in top_idx:
        source = metadata[idx]["source"]
        if source in seen:
            continue
        seen.add(source)
        results.append({
            "text": documents[idx],
            "source": source,
            "path": metadata[idx]["path"],
            "title": metadata[idx]["title"],
            "chunk_id": metadata[idx]["chunk_id"],
            "score": float(scores[idx]),
        })
        if len(results) >= top_k:
            break
    return results
