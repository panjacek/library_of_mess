"""Pure logic behind scripts/eval_search.py — retrieval-quality measurement.

Loads a user-maintained query set (JSON: ``{"queries": [{"text": ...,
"relevant": ["video_stem", ...]}]}``) and computes ranking metrics over
grouped search hits. No streamlit, no model runtime here — the eval script
wires real encoders around these functions; tests use plain data.

Metrics are trends to compare across runs (model swap, prompt templates,
frame density), not pass/fail gates: see docs/plans/ handoff and ADR 0001.
"""

import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class QuerySpec:
    """One labeled query: text plus the stems of videos that should surface."""

    text: str
    relevant: frozenset[str]


class QuerySetError(ValueError):
    """Raised when the query-set file is malformed."""


def load_query_set(path: Path) -> list[QuerySpec]:
    """Parse + validate the labeled query set; duplicate or empty queries rejected."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise QuerySetError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("queries"), list):
        raise QuerySetError(f"{path}: expected top-level {{'queries': [...]}}")

    specs: list[QuerySpec] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw["queries"]):
        if not isinstance(entry, dict):
            raise QuerySetError(f"{path}: query #{i} is not an object")
        text = str(entry.get("text", "")).strip()
        if not text:
            raise QuerySetError(f"{path}: query #{i} has an empty 'text'")
        if text in seen:
            raise QuerySetError(f"{path}: duplicate query '{text}'")
        seen.add(text)
        raw_relevant = entry.get("relevant", [])
        if not isinstance(raw_relevant, list):
            raise QuerySetError(f"{path}: query '{text}': 'relevant' must be a list of video stems")
        relevant = frozenset(stem for stem in (str(s).strip() for s in raw_relevant) if stem)
        specs.append(QuerySpec(text=text, relevant=relevant))
    if not specs:
        raise QuerySetError(f"{path}: no queries defined")
    return specs


def recall_at_k(ranked: Sequence[str], relevant: Collection[str], k: int) -> float:
    """Fraction of relevant videos present in the top-k ranked results."""
    wanted = frozenset(relevant)
    if not wanted:
        return 0.0
    top = frozenset(ranked[: max(k, 0)])
    return len(top & wanted) / len(wanted)


def first_relevant_rank(ranked: Sequence[str], relevant: Collection[str]) -> int | None:
    """1-based position of the first relevant hit, or None when none appear."""
    wanted = frozenset(relevant)
    for position, video in enumerate(ranked, start=1):
        if video in wanted:
            return position
    return None


def mrr(ranked: Sequence[str], relevant: Collection[str]) -> float:
    """Reciprocal rank of the first relevant hit; 0.0 when none appear."""
    rank = first_relevant_rank(ranked, relevant)
    return 1.0 / rank if rank else 0.0


def fuse_template_hits(hits_per_variant: Sequence[Sequence[tuple[str, float]]]) -> list[tuple[str, float, int]]:
    """Element-wise max fusion across prompt-template variants of one query.

    Each input is a ranked (stem, score) list for one phrasing variant; a
    stem's fused score is its best score over all variants. Returns
    (stem, best_score, winning_variant_index) sorted best-first — the variant
    index tells you which phrasing actually matched.
    """
    best: dict[str, tuple[float, int]] = {}
    for variant_idx, hits in enumerate(hits_per_variant):
        for stem, score in hits:
            known = best.get(stem)
            if known is None or score > known[0]:
                best[stem] = (score, variant_idx)
    return [(stem, score, idx) for stem, (score, idx) in sorted(best.items(), key=lambda kv: -kv[1][0])]


@dataclass(frozen=True)
class HitStats:
    """Per-query quality snapshot vs the corpus noise floor."""

    best_rank: int | None
    best_relevant_score: float | None
    top_score: float
    median_frame_score: float


def summarize_hits(
    grouped: Sequence[tuple[str, float, float]],
    relevant: Collection[str],
    all_scores: Sequence[float],
) -> HitStats:
    """Where/how strong relevant hits landed, against every raw frame score.

    `grouped` is the ranked per-video result (video, score, seconds);
    `all_scores` covers all raw frame hits for the same query so the median
    doubles as the noise-floor estimate for threshold tuning.
    """
    wanted = frozenset(relevant)
    best_rank = next((i for i, (video, _, _) in enumerate(grouped, start=1) if video in wanted), None)
    rel_scores = [score for video, score, _ in grouped if video in wanted]
    ordered = sorted(all_scores)
    return HitStats(
        best_rank=best_rank,
        best_relevant_score=max(rel_scores) if rel_scores else None,
        top_score=max((score for _, score, _ in grouped), default=0.0),
        median_frame_score=float(median(ordered)) if ordered else 0.0,
    )
