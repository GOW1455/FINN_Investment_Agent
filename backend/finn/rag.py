"""Page-cited retrieval over one document, with local embeddings and MMR.

Each document gets its own index file, so companies never mix. Chunks keep their page number,
which is what lets every claim downstream carry a citation.
"""
import hashlib

import numpy as np

from .config import DOCS

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None


def _embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME)
    return _model


def _embed(texts: list[str]) -> np.ndarray:
    vectors = np.array(list(_embedder().embed(texts, batch_size=32)), dtype=np.float32)
    return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)


def chunk_pages(pages: list[str], size: int = 1400, overlap: int = 200) -> list[dict]:
    """Split each page into overlapping character windows; a chunk never spans pages."""
    chunks = []
    for number, text in enumerate(pages, start=1):
        text = " ".join(text.split())
        if len(text) < 80:
            continue
        start = 0
        while start < len(text):
            chunks.append({"page": number, "text": text[start:start + size]})
            if start + size >= len(text):
                break
            start += size - overlap
    return chunks


def build(doc_key: str, pages: list[str]) -> dict:
    """Embed a document once; later calls load the saved index."""
    name = hashlib.sha1(f"{_MODEL_NAME}:{doc_key}".encode()).hexdigest()[:16]
    path = DOCS / f"{name}.npz"
    chunks = chunk_pages(pages)
    if path.exists():
        saved = np.load(path)
        if saved["vectors"].shape[0] == len(chunks):
            return {"chunks": chunks, "vectors": saved["vectors"]}
    vectors = _embed([c["text"] for c in chunks]) if chunks else np.zeros((0, 384), dtype=np.float32)
    np.savez_compressed(path, vectors=vectors)
    return {"chunks": chunks, "vectors": vectors}


def search(index: dict, query: str, k: int = 6, fetch_k: int = 24, diversity: float = 0.4) -> list[dict]:
    """Top-k chunks by maximal marginal relevance: relevant to the query, different from each other."""
    vectors = index["vectors"]
    if vectors.shape[0] == 0:
        return []
    query_vector = _embed([f"Represent this sentence for searching relevant passages: {query}"])[0]
    scores = vectors @ query_vector
    candidates = list(np.argsort(-scores)[:fetch_k])
    picked = []
    while candidates and len(picked) < k:
        if not picked:
            best = candidates[0]
        else:
            chosen = vectors[picked]
            best = max(candidates,
                       key=lambda i: (1 - diversity) * scores[i] - diversity * float(np.max(chosen @ vectors[i])))
        picked.append(best)
        candidates.remove(best)
    return [{**index["chunks"][i], "score": round(float(scores[i]), 3)} for i in picked]
