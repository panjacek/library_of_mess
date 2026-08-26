"""One-shot health check for the embedding stack — does text search actually match?

No metrics files, no CSVs: prints thumbnail paths + scores so a human can
eyeball whether obvious queries find obvious content. Uses the exact same
encoders/preprocessing as the app.

Usage:
    uv run python scripts/sanity_check.py
    uv run python scripts/sanity_check.py --anchor DJI_20260815140445_0023_D
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from library_of_mess import config
from library_of_mess.embeddings import l2_normalize
from library_of_mess.encoders import build_encoders, configured_model_id

QUERIES = [
    "a photo of mountains",
    "a photo of a mountain panorama",
    "a photo of a bicycle",
    "a photo of a forest path",
    "red gloves",
    "a photo of an indoor kitchen",
]
DEFAULT_ANCHOR = "DJI_20260815140445_0023_D"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that embeddings actually match obvious content.")
    parser.add_argument("--thumbs-dir", type=Path, default=None, help="thumbnail cache dir (default: configured)")
    parser.add_argument("--limit", type=int, default=30, help="max thumbnails to test (default: 30)")
    parser.add_argument("--anchor", default=DEFAULT_ANCHOR, help="video stem known to show mountains")
    args = parser.parse_args()

    thumbs_dir = args.thumbs_dir or config.thumbnails_dir()
    all_thumbs = sorted(thumbs_dir.glob("*.jpg"))
    if not all_thumbs:
        print(f"error: no thumbnails in {thumbs_dir}", file=sys.stderr)
        return 1
    # spread across the whole cache (whole shoots would look like near-duplicates)
    step = max(1, len(all_thumbs) // max(args.limit, 2))
    thumbs = all_thumbs[::step][: max(args.limit, 2)]
    stems = [p.stem for p in thumbs]
    if args.anchor not in stems:
        anchor_file = thumbs_dir / f"{args.anchor}.jpg"
        if anchor_file.exists():
            thumbs[-1] = anchor_file
            stems[-1] = args.anchor
    print(f"{len(thumbs)} thumbnails from {thumbs_dir}")

    print("Loading encoders ... (first run downloads model weights)")
    try:
        encode_images, encode_texts = build_encoders()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"model: {configured_model_id()}\n")

    # --- A) vision tower self-test ---
    vectors = l2_normalize(encode_images(thumbs))
    gram = vectors @ vectors.T
    n = len(thumbs)
    off_diag = gram[~np.eye(n, dtype=bool)]
    self_min = float(np.min(np.diag(gram)))
    print("A) vision self-test")
    print(f"   self-similarity min: {self_min:.3f} (must be ~1.0)")
    print(f"   different images:    mean {off_diag.mean():.3f}, max {off_diag.max():.3f} (expect mean <0.4)")
    if self_min < 0.99:
        print("   SUSPECT: image embeddings look broken (self-similarity below 1.0)")
    print()

    # --- B) text -> image ranking ---
    query_vectors = l2_normalize(encode_texts(QUERIES))
    anchor_row = stems.index(args.anchor) if args.anchor in stems else None
    print("B) text queries -> top-5 thumbnails")
    for query, qvec in zip(QUERIES, query_vectors):
        scores = vectors @ qvec
        order = np.argsort(-scores)[:5]
        print(f"  '{query}'")
        for pos, idx in enumerate(order, start=1):
            marker = " <-- anchor" if anchor_row is not None and idx == anchor_row else ""
            print(f"    {pos}. {scores[idx]:.3f}  {stems[idx]}{marker}")
        if anchor_row is not None:
            rank = int((scores > scores[anchor_row]).sum()) + 1
            print(f"    anchor '{args.anchor}': score {scores[anchor_row]:.3f}, rank {rank}/{n}")
    print()
    print("Eyeball check: do the top paths match the query subject?")
    print("(kitchen control should score lowest across all queries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
