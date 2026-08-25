"""Tests for the embedding store: incremental cache, cosine search, persistence."""

from pathlib import Path

import numpy as np
import pytest

from library_of_mess import config
from library_of_mess.embeddings import (
    ImageEncoder,
    l2_normalize,
    load_embeddings,
    save_embeddings,
    search,
    update_embeddings,
)


def name_encoder(paths: list[Path], calls: list[int] | None = None) -> np.ndarray:
    """Deterministic fake encoder: 3-dim vector derived from filename length."""
    if calls is not None:
        calls.append(len(paths))
    vecs = np.array([[float(len(p.stem)), 1.0, 0.0] for p in paths])
    return l2_normalize(vecs)


def thumb(tmp_path: Path, stem: str) -> Path:
    path = tmp_path / f"{stem}.jpg"
    path.write_bytes(b"fake")
    return path


def counting_encoder(calls: list[int]) -> ImageEncoder:
    def encode(paths: list[Path]) -> np.ndarray:
        return name_encoder(paths, calls)

    return encode


def read_store(path: Path) -> tuple[list[str], np.ndarray]:
    loaded = load_embeddings(path)
    assert loaded is not None
    return loaded


def test_l2_normalize_rows_unit_and_zero_safe() -> None:
    vectors = np.array([[3.0, 4.0], [0.0, 0.0]])
    normalized = l2_normalize(vectors)
    assert np.allclose(np.linalg.norm(normalized[0]), 1.0)
    assert np.allclose(normalized[1], 0.0)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "store.npz"
    stems = ["b", "a"]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    save_embeddings(store, stems, vectors)
    loaded_stems, loaded_vectors = read_store(store)
    assert loaded_stems == stems
    assert np.array_equal(loaded_vectors, vectors)


def test_load_missing_store_returns_none(tmp_path: Path) -> None:
    assert load_embeddings(tmp_path / "nope.npz") is None


def test_update_encodes_new_and_sorts(tmp_path: Path) -> None:
    calls: list[int] = []
    store = config.embeddings_path()
    update_embeddings([thumb(tmp_path, "b"), thumb(tmp_path, "a")], counting_encoder(calls), store)
    stems, vectors = read_store(store)
    assert stems == ["a", "b"]
    assert calls == [2]
    assert vectors.shape == (2, 3)


def test_update_is_incremental(tmp_path: Path) -> None:
    calls: list[int] = []
    encode = counting_encoder(calls)
    store = config.embeddings_path()

    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "b")], encode, store)
    assert calls == [2]

    # nothing new: no encoder invocations at all
    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "b")], encode, store)
    assert calls == [2]

    # one new thumb: only that one encoded, old vectors preserved
    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "b"), thumb(tmp_path, "ccc")], encode, store)
    assert calls == [2, 1]
    stems, _ = read_store(store)
    assert stems == ["a", "b", "ccc"]


def test_update_drops_stale_entries(tmp_path: Path) -> None:
    encode: ImageEncoder = lambda p: name_encoder(p)  # noqa: E731
    store = config.embeddings_path()
    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "gone")], encode, store)

    update_embeddings([thumb(tmp_path, "a")], encode, store)
    stems, vectors = read_store(store)
    assert stems == ["a"]
    assert vectors.shape[0] == 1


def test_update_rebuilds_store_when_encoder_dim_changes(tmp_path: Path) -> None:
    store = config.embeddings_path()
    calls2: list[int] = []

    def dim2_encoder(paths: list[Path]) -> np.ndarray:
        calls2.append(len(paths))
        return l2_normalize(np.array([[float(len(p.stem)), 1.0] for p in paths]))

    calls3: list[int] = []
    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "bb")], counting_encoder(calls3), store)
    _, vectors = read_store(store)
    assert vectors.shape[1] == 3

    # one NEW thumbnail forces a re-encode; the dim mismatch must trigger a
    # full rebuild so old and new vector spaces never mix
    update_embeddings([thumb(tmp_path, "a"), thumb(tmp_path, "bb"), thumb(tmp_path, "ccc")], dim2_encoder, store)
    stems, vectors = read_store(store)
    assert stems == ["a", "bb", "ccc"]
    assert vectors.shape == (3, 2)
    assert calls2 == [1, 3]


def test_search_orders_best_first(tmp_path: Path) -> None:
    store = config.embeddings_path()
    update_embeddings(
        [thumb(tmp_path, "aa"), thumb(tmp_path, "aaaa"), thumb(tmp_path, "x")],
        lambda p: name_encoder(p),
        store,
    )
    stems, vectors = read_store(store)

    query = name_encoder([Path("aaa.jpg")])[0]
    results = search(query, stems, vectors, k=2)
    assert len(results) == 2
    scores = [score for _, score in results]
    assert scores[0] >= scores[1]
    assert {stem for stem, _ in results} <= {"aa", "aaaa", "x"}


def test_search_empty_store_returns_empty() -> None:
    assert search(np.zeros(3), [], np.zeros((0, 0), dtype=np.float32)) == []


def test_search_dim_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="dim"):
        search(np.ones(5), ["a"], np.ones((1, 3), dtype=np.float32))
