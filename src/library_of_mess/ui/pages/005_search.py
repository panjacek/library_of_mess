"""Semantic search: text query -> ranked moments across whole videos -> play.

Nothing indexes on page open. Indexing happens only when you press the
button: each press samples at most SEARCH_INDEX_BUDGET new videos and embeds
all not-yet-embedded frames. Pure logic lives in `moment_search.py`.
"""

import importlib.util
from pathlib import Path

import numpy as np
import streamlit as st
from streamlit.logger import get_logger

from library_of_mess import config
from library_of_mess.database import resolve_media_path
from library_of_mess.embeddings import (
    load_embeddings,
    search,
    update_embeddings,
)
from library_of_mess.encoders import configured_model_id, weights_cached
from library_of_mess.moment_search import (
    collect_frames,
    group_hits,
    plan_sampling,
    sampling_timestamps,
    seconds_for_frames,
)
from library_of_mess.thumbnails import generate_search_frames, search_frames_dir
from library_of_mess.ui.helpers import ensure_db_loaded, load_encoders

st.set_page_config(page_title="Library of Mess - Search", page_icon="🔍", layout="wide")

logger = get_logger(__name__)

EXTRA_MISSING = importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None

if EXTRA_MISSING:
    st.warning("Semantic search needs the optional ML stack (not installed).")
    st.code("uv sync --extra embeddings", language="bash")
    st.stop()

db = ensure_db_loaded()
lengths = {
    str(row["path"]): float(row["length"]) for _, row in db.iterrows() if row["length"] and float(row["length"]) > 0
}


def _empty_store() -> tuple[list[str], np.ndarray]:
    return [], np.zeros((0, 0), dtype=np.float32)


query = st.text_input(
    "Describe what you're looking for",
    placeholder="rainy descent, group ride, forest singletrack …",
)
k = st.slider("Max videos", 4, 24, 12)
name_filter = st.text_input(
    "Limit to videos whose name contains",
    placeholder="e.g. 202608 — empty means whole library",
)

library_paths = {Path(p).stem: str(p) for p in db["path"].astype(str)}
needle = name_filter.strip().lower()
videos = {s: p for s, p in library_paths.items() if not needle or needle in s.lower()}
frames_root = search_frames_dir()
frames_root.mkdir(parents=True, exist_ok=True)

if not videos:
    st.warning(f"No videos match '{name_filter.strip()}' — nothing to index or search.")
    st.stop()


def _timestamps_for(stem: str) -> list[float]:
    """~SEARCH_FRAMES_PER_VIDEO timestamps spread over the video duration."""
    return sampling_timestamps(
        lengths.get(videos[stem], 0.0),
        config.search_frames_per_video(),
        config.search_frame_interval(),
    )


plan = plan_sampling(videos, frames_root)
for stem in plan.duplicate_stems:
    st.warning(f"Duplicate stem '{stem}' exists in multiple folders — results may mix them up")

scope_note = f" · corpus {len(videos)}/{len(library_paths)} by name filter" if needle else ""
coverage = (
    f"Coverage: {plan.covered_count}/{len(videos)} videos sampled"
    f"{scope_note} · ~{config.search_frames_per_video()} frames per video by duration"
)
st.caption(coverage)

usable_frames, orphans = collect_frames(frames_root, videos)
key_seconds = seconds_for_frames(
    usable_frames,
    {stem: lengths.get(path, 0.0) for stem, path in videos.items()},
    config.search_frames_per_video(),
    config.search_frame_interval(),
)
stored = load_embeddings(config.embeddings_path())
stems, matrix = stored if stored is not None else _empty_store()
embedded_keys = set(stems)
missing_frames = [p for p in usable_frames if p.stem not in embedded_keys]

# --- explicit indexing only ---
if plan.todo or missing_frames:
    todo_count = len(plan.todo)
    budget = int(
        st.number_input(
            "Videos to sample per press",
            min_value=0,
            max_value=max(todo_count, 1),
            value=min(max(config.search_index_budget(), 0), max(todo_count, 1)),
            help="Cap on new videos sampled per press (SEARCH_INDEX_BUDGET sets the "
            "default). Embedding of already-sampled frames is not capped.",
        )
    )
    label = f"📥 Index now — {todo_count} video(s) to sample · {len(missing_frames)} frame(s) to embed"
    if st.button(label, type="primary"):
        batch = plan.todo[:budget]
        failures: list[str] = []
        if batch:
            progress = st.progress(0.0, text=f"Sampling {len(batch)} videos…")
            for done, stem in enumerate(batch):
                try:
                    generate_search_frames(
                        resolve_media_path(videos[stem]),
                        frames_root,
                        _timestamps_for(stem),
                    )
                except Exception as exc:
                    logger.warning("frame sampling failed on %s: %s", stem, exc)
                    failures.append(stem)
                progress.progress((done + 1) / len(batch), text=f"Sampling {done + 1}/{len(batch)}")
            progress.empty()
        if failures:
            st.error(f"{len(failures)} decode failure(s): {', '.join(failures[:5])}")

        usable_now, _orphan_count = collect_frames(frames_root, videos)
        newly_usable = [p for p in usable_now if p.stem not in embedded_keys]
        if not usable_now or (not newly_usable and not embedded_keys):
            st.error(
                "Sampling produced no usable frames — store left untouched. Check the log for per-video ffmpeg errors."
            )
            st.stop()

        spinner = "Embedding…" if weights_cached() else "Embedding… first run downloads Google SigLIP2 (~1.1GB)"
        with st.spinner(spinner):
            encode_images, _text_enc = load_encoders()
            update_embeddings(
                usable_now,
                encode_images,
                config.embeddings_path(),
                batch_size=64,
                model_id=configured_model_id(),
            )
        st.rerun()
else:
    st.success("Everything sampled and embedded.")

indexed_videos = {s.rsplit(".f", 1)[0] for s in stems}
status = f"Store: {len(stems)} frames · {len(indexed_videos)} videos · model {configured_model_id().split('/')[-1]}"
if orphans:
    status += f" · {orphans} frames outside current filter (ignored)"
st.caption(status)

if not query.strip():
    st.info("Type a query to search by look.")
    st.stop()

if not stems:
    st.warning("Press 📥 Index now first — the store is empty.")
    st.stop()

_img_enc, encode_texts = load_encoders()
raw_hits = search(encode_texts([query.strip()])[0], stems, matrix, k=max(k * 6, 36))
grouped = group_hits(raw_hits, top_k=k, seconds_for=key_seconds, corpus=set(videos))

if not grouped:
    st.warning(f"No matches among the {len(stems)} indexed frames. Index more, or widen the name filter.")
    st.stop()

st.caption(f"Top {len(grouped)} of {len(stems)} indexed frames")

# normalize scores to a 0-1 scale so the UI shows relative match strength
# instead of raw SigLIP2 cosine (0-0.15, meaningless as absolute value)
scores = [s for _, s, _ in grouped]
s_min, s_max = scores[0], scores[-1]  # grouped is sorted best-first
span = s_max - s_min if s_max != s_min else 1.0

cols = st.columns(3)
for pos, (video, score, timestamp) in enumerate(grouped):
    minutes, seconds = divmod(int(timestamp), 60)
    with cols[pos % 3]:
        preview: Path | None = next(iter(sorted(frames_root.glob(f"{video}.f*.jpg"))), None)
        if preview is not None:
            st.image(str(preview))
        relative = (score - s_min) / span if span else 1.0
        st.progress(relative, text=f"#{pos + 1}")
        st.caption(f"{video} · at {minutes}:{seconds:02d}")
        if st.button("▶ Play from moment", key=f"play_{video}"):
            st.session_state["play_video"] = videos[video]
            st.session_state["play_video_start"] = timestamp
            st.switch_page("app.py")
