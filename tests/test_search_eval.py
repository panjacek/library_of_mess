"""Tests for the pure eval-harness logic (no streamlit, no ML)."""

import json
from pathlib import Path

import pytest

from library_of_mess.search_eval import (
    QuerySetError,
    first_relevant_rank,
    fuse_template_hits,
    load_query_set,
    mrr,
    recall_at_k,
    summarize_hits,
)


def _write_labels(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(payload))
    return path


def test_load_query_set_parses_and_normalizes(tmp_path: Path) -> None:
    path = _write_labels(
        tmp_path,
        {
            "_comment": "ignored key",
            "queries": [
                {"text": "  rainy descent ", "relevant": [" a ", "b.mp4", ""]},
                {"text": "group ride"},
            ],
        },
    )

    specs = load_query_set(path)

    assert [s.text for s in specs] == ["rainy descent", "group ride"]
    assert specs[0].relevant == frozenset({"a", "b.mp4"})
    assert specs[1].relevant == frozenset()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"queries": {}},
        {"queries": ["not an object"]},
        {"queries": [{"text": ""}]},
        {"queries": [{"text": "a"}, {"text": "a"}]},
        {"queries": [{"text": "a", "relevant": "b"}]},
    ],
)
def test_load_query_set_rejects_malformed(tmp_path: Path, payload: object) -> None:
    path = _write_labels(tmp_path, payload)  # type: ignore[arg-type]

    with pytest.raises(QuerySetError):
        load_query_set(path)


def test_load_query_set_rejects_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    path.write_text("{not json")

    with pytest.raises(QuerySetError):
        load_query_set(path)


def test_recall_at_k_counts_top_k_overlap() -> None:
    ranked = ["a", "x", "b", "y"]

    assert recall_at_k(ranked, {"a", "b", "c"}, k=3) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, {"a", "b"}, k=1) == pytest.approx(0.5)
    assert recall_at_k(ranked, set(), k=3) == 0.0
    assert recall_at_k(ranked, {"z"}, k=0) == 0.0


def test_first_relevant_rank_and_mrr() -> None:
    ranked = ["x", "y", "a", "z"]

    assert first_relevant_rank(ranked, {"a"}) == 3
    assert mrr(ranked, {"a"}) == pytest.approx(1 / 3)
    assert first_relevant_rank(ranked, {"a", "z"}) == 3
    assert mrr(["x", "y"], {"a"}) == 0.0
    assert mrr([], {"a"}) == 0.0


def test_fuse_template_hits_takes_best_variant_per_stem() -> None:
    fused = fuse_template_hits(
        [
            [("b", 0.4), ("a", 0.2)],
            [("a", 0.9), ("c", 0.1)],
            [("a", 0.5), ("b", 0.7)],
        ]
    )

    assert fused[0] == ("a", pytest.approx(0.9), 1)  # won by variant #1
    assert fused[1] == ("b", pytest.approx(0.7), 2)
    assert fused[2] == ("c", pytest.approx(0.1), 1)


def test_fuse_template_handles_empty_variants() -> None:
    assert fuse_template_hits([]) == []
    assert fuse_template_hits([[], []]) == []


def test_summarize_hits_locates_relevant_against_noise_floor() -> None:
    grouped = [("a", 0.9, 10.0), ("b", 0.5, 20.0), ("c", 0.4, 30.0)]

    stats = summarize_hits(grouped, {"b"}, [0.1, 0.2, 0.5, 0.9])

    assert stats.best_rank == 2
    assert stats.best_relevant_score == pytest.approx(0.5)
    assert stats.top_score == pytest.approx(0.9)
    assert stats.median_frame_score == pytest.approx(0.35)


def test_summarize_hits_handles_nothing_relevant_or_empty() -> None:
    stats = summarize_hits([("a", 0.9, 1.0)], {"zzz"}, [0.9])
    assert stats.best_rank is None
    assert stats.best_relevant_score is None
    assert stats.top_score == pytest.approx(0.9)

    empty = summarize_hits([], {"a"}, [])
    assert empty.top_score == 0.0 and empty.median_frame_score == 0.0
