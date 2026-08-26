"""Embedding store + cosine search for semantic video lookup.

Pure array-in/array-out logic — no streamlit, no model runtime here. Encoders
are injected as plain callables so tests use fake vectors and a future model
backend stays swappable (research plan: docs/plans/2026-08-25_plan_embedding_research.md).
"""

import os
from collections.abc import Callable
from pathlib import Path

import numpy as np

# An encoder takes a batch and returns an (n, dim) float32 array.
# Image/query spaces must be aligned by whatever model produces them.
ImageEncoder = Callable[[list[Path]], np.ndarray]
TextEncoder = Callable[[list[str]], np.ndarray]


def current_model_id() -> str:
    """Identity of the embedding model the store must match (empty = untracked)."""
    return os.environ.get("EMBEDDINGS_MODEL", "")


def _read_model_id(store_path: Path) -> str:
    if not store_path.exists():
        return ""
    with np.load(store_path) as data:
        return str(data["model_id"][0]) if "model_id" in data else ""


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization; zero rows pass through untouched."""
    vectors = vectors.astype(np.float32, copy=True)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


def load_embeddings(store_path: Path) -> tuple[list[str], np.ndarray] | None:
    """Load (stems, normalized vectors) or None when the store does not exist yet."""
    if not store_path.exists():
        return None
    with np.load(store_path) as data:
        return list(data["stems"].astype(str)), data["vectors"].astype(np.float32)


def save_embeddings(store_path: Path, stems: list[str], vectors: np.ndarray, model_id: str = "") -> None:
    """Persist the embedding store next to the thumbnail cache."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    # pid suffix: two concurrent sessions must not share one tmp file
    tmp = store_path.with_suffix(f".{os.getpid()}.tmp.npz")
    np.savez(tmp, stems=np.array(stems), vectors=vectors.astype(np.float32), model_id=np.array([model_id]))
    tmp.replace(store_path)


def update_embeddings(
    thumb_paths: list[Path],
    encode_images: ImageEncoder,
    store_path: Path,
    batch_size: int | None = None,
    model_id: str = "",
) -> tuple[list[str], np.ndarray]:
    """Sync the embedding store with the thumbnail set, encoding only what is new.

    Entries whose thumbnail disappeared are dropped; everything else is kept
    cached, so repeated builds only cost the newly added videos. The store is
    rebuilt whenever the encoder's identity (`model_id`) or output dimension
    changes — vectors from different models must never mix, even when their
    dims happen to match. `batch_size` encodes missing items in chunks (bounds
    peak memory / gives progress loops something to chew on) without extra
    store writes.

    Returns (sorted stems, row-aligned normalized vectors).
    """
    stored: dict[str, np.ndarray] = {}
    current = load_embeddings(store_path)
    if current is not None:
        stored = dict(zip(current[0], current[1]))
    stale_model = bool(model_id) and _read_model_id(store_path) != model_id
    if stale_model:
        stored = {}

    wanted = {p.stem: p for p in thumb_paths}
    stored = {stem: vec for stem, vec in stored.items() if stem in wanted}
    missing = [path for stem, path in sorted(wanted.items()) if stem not in stored]

    if missing:
        chunks = (
            [missing]
            if not batch_size or batch_size <= 0
            else [missing[i : i + batch_size] for i in range(0, len(missing), batch_size)]
        )
        vectors = np.vstack([l2_normalize(encode_images(chunk)) for chunk in chunks])
        if stored:
            existing_dim = next(iter(stored.values())).shape[0]
            if vectors.shape[1] != existing_dim:
                # encoder changed: re-embed everything so dims stay consistent
                stored = {}
                missing = sorted(wanted.values())
                vectors = l2_normalize(encode_images(missing))
        for path, vec in zip(missing, vectors):
            stored[path.stem] = vec

    stems = sorted(stored)
    if stems:
        matrix = np.stack([stored[stem] for stem in stems])
    else:
        matrix = np.zeros((0, 0), dtype=np.float32)
    save_embeddings(store_path, stems, matrix, model_id=model_id)
    return stems, matrix


def search(query_vector: np.ndarray, stems: list[str], vectors: np.ndarray, k: int = 12) -> list[tuple[str, float]]:
    """Top-k (stem, cosine score) pairs, best first. Empty store yields []."""
    if not stems or vectors.shape[0] != len(stems) or vectors.shape[0] == 0:
        return []
    query = l2_normalize(np.asarray(query_vector, dtype=np.float32).reshape(1, -1))[0]
    if query.shape[0] != vectors.shape[1]:
        raise ValueError(f"query dim {query.shape[0]} != embedding dim {vectors.shape[1]}")
    scores = vectors @ query
    order = np.argsort(-scores)[: max(k, 0)]
    return [(stems[i], float(scores[i])) for i in order]
