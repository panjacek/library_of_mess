"""Retrieval-quality harness for semantic moment search.

Runs the exact indexing + query pipeline behind ui/pages/005_search.py against
the real library, ranks a labeled query set, and dumps per-query results plus
metrics to timestamped CSVs (under the embeddings cache dir). Run before and
after every tuning change and diff the outputs — without it every tweak is
vibes (handoff plan in docs/plans/, ADR 0001 follow-up).

Usage:
    cp scripts/eval_labels.example.json eval_labels.json   # then fill 'relevant'
    uv run python scripts/eval_search.py --from-thumbs     # fast: poster-thumb cache
    uv run python scripts/eval_search.py                   # whole-video moment pipeline
    uv run python scripts/eval_search.py --filter 202608   # subset by name
    uv run python scripts/eval_search.py --labels my.json --k 5

Modes:
  --from-thumbs  corpus = existing THUMBNAILS_DIR/*.jpg (one poster frame per
                 video). No ffmpeg, no database, no source media needed —
                 stale db rows can never break the run. Uses its own embedding
                 store (*_thumbs.npz), so frame-level entries stay untouched.
  default        whole-video moment pipeline: samples SEARCH_FRAMES_PER_VIDEO
                 frames per video via ffmpeg (~2 img/s on cpu, resumable via
                 the npz cache), groups best moment per video.
"""

import argparse
import csv
import sys
import time
from pathlib import Path


from library_of_mess import config, database
from library_of_mess.database import resolve_media_path
from library_of_mess.embeddings import search, update_embeddings
from library_of_mess.encoders import build_encoders, configured_model_id, weights_cached
from library_of_mess.moment_search import (
    collect_frames,
    group_hits,
    plan_sampling,
    sampling_timestamps,
    seconds_for_frames,
)
from library_of_mess.search_eval import (
    HitStats,
    QuerySpec,
    fuse_template_hits,
    load_query_set,
    mrr,
    recall_at_k,
    summarize_hits,
)
from library_of_mess.thumbnails import generate_search_frames, search_frames_dir

DEFAULT_LABELS = Path("eval_labels.json")


def build_corpus(args: argparse.Namespace) -> tuple[dict[str, str], dict[str, float], list[Path], Path, int]:
    """Return (videos, durations, frames_to_embed, store_path, frames_per_video).

    `videos` maps stem -> display id; `durations` feeds timestamp math (empty in
    thumbs mode); `frames_to_embed` are the images ranked by the harness;
    `store_path` keeps both modes' npz caches separate.
    """
    needle = args.filter.strip().lower()
    embeddings_file = config.embeddings_path()
    if args.from_thumbs:
        thumbs_root = config.thumbnails_dir()
        matches = sorted(p for p in thumbs_root.glob("*.jpg") if not needle or needle in p.stem.lower())
        videos = {p.stem: p.stem for p in matches}
        return (
            videos,
            {},
            matches,
            embeddings_file.with_name(embeddings_file.stem + "_thumbs.npz"),
            1,
        )
    db = database.load_db(config.db_path())
    if db is None or db.empty:
        print(f"error: no database at {config.db_path()} — scan your library first", file=sys.stderr)
        raise SystemExit(1)
    lengths = {
        str(row["path"]): float(row["length"]) for _, row in db.iterrows() if row["length"] and float(row["length"]) > 0
    }
    videos = {Path(p).stem: str(p) for p in db["path"].astype(str) if not needle or needle in Path(p).stem.lower()}
    return videos, lengths, [], embeddings_file, config.search_frames_per_video()


def sample_missing(videos: dict[str, str], lengths: dict[str, float]) -> None:
    """ffmpeg-sample every corpus video that has no search frames yet."""
    frames_root = search_frames_dir()
    frames_root.mkdir(parents=True, exist_ok=True)
    plan = plan_sampling(videos, frames_root)
    for stem in plan.duplicate_stems:
        print(f"warning: duplicate stem across folders: {stem} — results may mix them up", file=sys.stderr)
    if plan.todo:
        print(f"Sampling {len(plan.todo)} video(s) ...")
    failures = []
    for done, stem in enumerate(plan.todo, start=1):
        timestamps = sampling_timestamps(
            lengths.get(videos[stem], 0.0),
            config.search_frames_per_video(),
            config.search_frame_interval(),
        )
        try:
            generate_search_frames(resolve_media_path(videos[stem]), frames_root, timestamps)
        except Exception as exc:  # noqa: BLE001 — one bad file must not kill the run
            print(f"warning: frame sampling failed on {stem}: {exc}", file=sys.stderr)
            failures.append(stem)
        if done % 10 == 0 or done == len(plan.todo):
            print(f"  sampled {done}/{len(plan.todo)}")
    if failures:
        print(f"warning: {len(failures)} decode failure(s): {', '.join(failures[:5])}", file=sys.stderr)


# caption-style phrasings for the --prompt-templates experiment: bare nouns
# score near SigLIP2's noise floor; fused max-over-variants is the workaround
PROMPT_TEMPLATES = [
    "{}",
    "a photo of {}",
    "a photo of a {}",
    "a video still of {}",
]


def rank_query(
    spec: QuerySpec,
    raw_hits: list[tuple[str, float]],
    from_thumbs: bool,
    key_seconds: dict[str, float],
    corpus: set[str],
    k: int,
) -> tuple[list[tuple[str, float, float]], HitStats]:
    """Top-k per-video hits for one query, plus its quality stats."""
    if from_thumbs:
        # one image per video: the ranking already is per-video
        grouped = [(stem, score, 0.0) for stem, score in raw_hits[:k]]
    else:
        grouped = group_hits(raw_hits, top_k=k, seconds_for=key_seconds, corpus=corpus)
    return grouped, summarize_hits(grouped, spec.relevant, [score for _, score in raw_hits])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate semantic moment-search quality on the real library.")
    parser.add_argument(
        "--labels", type=Path, default=DEFAULT_LABELS, help=f"labeled query set JSON (default: {DEFAULT_LABELS})"
    )
    parser.add_argument("--filter", default="", help="only index/search videos whose stem contains this substring")
    parser.add_argument("--k", type=int, default=5, help="videos to rank per query (default: 5)")
    parser.add_argument(
        "--from-thumbs",
        action="store_true",
        help="evaluate on the existing poster-thumbnail cache instead of sampled video frames (no ffmpeg, no database)",
    )
    parser.add_argument(
        "--prompt-templates",
        action="store_true",
        help="encode each query as caption-style phrasings and fuse by max score per video",
    )
    args = parser.parse_args()

    try:
        specs = load_query_set(Path(args.labels))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    videos, lengths, frames_override, store_path, density = build_corpus(args)
    if not videos:
        where = config.thumbnails_dir() if args.from_thumbs else f"filter '{args.filter}'"
        print(f"error: no videos match ({where})", file=sys.stderr)
        return 1

    if args.from_thumbs:
        usable_frames = frames_override
        print(f"Corpus: {len(usable_frames)} poster thumbnails from {config.thumbnails_dir()}")
    else:
        sample_missing(videos, lengths)
        usable_frames, _orphans = collect_frames(search_frames_dir(), videos)

    if not usable_frames:
        print("error: no usable images — nothing to evaluate", file=sys.stderr)
        return 1

    print(
        "Loading encoders ... (first run downloads model weights)" if not weights_cached() else "Loading encoders ..."
    )
    encode_images, encode_texts = build_encoders()
    stems, matrix = update_embeddings(
        usable_frames,
        encode_images,
        store_path,
        batch_size=64,
        model_id=configured_model_id(),
    )
    key_seconds = (
        {}
        if args.from_thumbs
        else seconds_for_frames(
            usable_frames,
            {stem: lengths.get(path, 0.0) for stem, path in videos.items()},
            config.search_frames_per_video(),
            config.search_frame_interval(),
        )
    )
    indexed_videos = set(stems) if args.from_thumbs else {s.rsplit(".f", 1)[0] for s in stems}
    model_id = configured_model_id()
    print(f"Store: {len(stems)} images · {len(indexed_videos)} videos · {density} frame(s)/video · model {model_id}")

    # --- rank every query, dump results + summary ---
    variants = PROMPT_TEMPLATES if args.prompt_templates else ["{}"]
    print(f"Queries: {len(specs)} × {len(variants)} prompt variant(s)" + (f" {variants}" if len(variants) > 1 else ""))
    vectors = encode_texts([variant.format(spec.text) for spec in specs for variant in variants])
    out_dir = config.embeddings_path().parent / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    result_rows = []
    summary_rows = []
    per_spec = len(variants)
    for spec_idx, spec in enumerate(specs):
        hits_per_variant = [
            search(vectors[spec_idx * per_spec + v], stems, matrix, k=max(args.k * 6, 36)) for v in range(per_spec)
        ]
        winning_prompts: dict[str, str] = {}
        if per_spec == 1:
            raw_hits = hits_per_variant[0]
        else:
            fused = fuse_template_hits(hits_per_variant)
            raw_hits = [(stem, score) for stem, score, _ in fused]
            winning_prompts = {stem: PROMPT_TEMPLATES[idx] for stem, _, idx in fused}
        grouped, stats = rank_query(spec, raw_hits, args.from_thumbs, key_seconds, set(videos), args.k)
        for rank, (video, score, seconds) in enumerate(grouped, start=1):
            result_rows.append(
                {
                    "query": spec.text,
                    "rank": rank,
                    "video": video,
                    "score": f"{score:.4f}",
                    "seconds": f"{seconds:.1f}",
                    "relevant": "y" if video in spec.relevant else "",
                    "prompt": winning_prompts.get(video, ""),
                    "model_id": model_id,
                    "frames_per_video": density,
                    "k": args.k,
                }
            )
        summary_rows.append(
            {
                "query": spec.text,
                "n_relevant": len(spec.relevant),
                "recall@k": round(recall_at_k([v for v, _, _ in grouped], spec.relevant, args.k), 3),
                "mrr": round(mrr([v for v, _, _ in grouped], spec.relevant), 3),
                "best_rank": stats.best_rank or "",
                "best_relevant_score": "" if stats.best_relevant_score is None else f"{stats.best_relevant_score:.4f}",
                "top_score": f"{stats.top_score:.4f}",
                "median_frame_score": f"{stats.median_frame_score:.4f}",
                "model_id": model_id,
                "frames_per_video": density,
                "k": args.k,
            }
        )

    suffix = "_thumbs" if args.from_thumbs else ""
    results_path = out_dir / f"{stamp}{suffix}_results.csv"
    summary_path = out_dir / f"{stamp}{suffix}_summary.csv"
    # literal fieldnames: result_rows can be empty when every grouped hit fell
    # outside the corpus (e.g. narrow --filter over a store built unfiltered)
    result_fields = [
        "query",
        "rank",
        "video",
        "score",
        "seconds",
        "relevant",
        "prompt",
        "model_id",
        "frames_per_video",
        "k",
    ]
    summary_fields = [
        "query",
        "n_relevant",
        "recall@k",
        "mrr",
        "best_rank",
        "best_relevant_score",
        "top_score",
        "median_frame_score",
        "model_id",
        "frames_per_video",
        "k",
    ]
    with results_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=result_fields)
        writer.writeheader()
        writer.writerows(result_rows)
    with summary_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"\n{'query':<28} rel recall@{args.k}  mrr   best  top     median")
    for row in summary_rows:
        best = row["best_rank"]
        print(
            f"{row['query']:<28} {row['n_relevant']:>3} "
            f"{row['recall@k']:>8}  {row['mrr']:<5} {str(best):<5} {row['top_score']}  {row['median_frame_score']}"
        )
    print(f"\nresults:   {results_path}")
    print(f"summary:   {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
