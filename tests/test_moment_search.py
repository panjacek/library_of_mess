"""Tests for the pure moment-search indexing logic (no streamlit, no ML)."""

from pathlib import Path

from library_of_mess.moment_search import (
    collect_frames,
    frame_timestamp,
    group_hits,
    plan_sampling,
    sampling_timestamps,
    seconds_for_frames,
)


def _make_frames(frames_root: Path, video_stem: str, count: int) -> list[Path]:
    frames_root.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        p = frames_root / f"{video_stem}.f{i:04d}.jpg"
        p.write_bytes(b"jpg")
        paths.append(p)
    return paths


def test_plan_sampling_fresh_dir_everything_todo(tmp_path: Path) -> None:
    videos = {"a": "a.mp4", "b": "b.mp4"}

    plan = plan_sampling(videos, tmp_path / "_search")

    assert plan.todo == ["a", "b"]
    assert plan.covered_count == 0
    assert plan.duplicate_stems == []


def test_plan_sampling_recognizes_existing_frames(tmp_path: Path) -> None:
    videos = {"a": "a.mp4", "b": "b.mp4"}
    _make_frames(tmp_path / "_search", "a", 3)

    plan = plan_sampling(videos, tmp_path / "_search")

    assert plan.todo == ["b"]
    assert plan.covered == {"a"}


def test_collect_frames_filters_orphans_and_counts_them(tmp_path: Path) -> None:
    _make_frames(tmp_path, "in_corpus", 2)
    _make_frames(tmp_path, "orphan_video", 5)
    corpus = {"in_corpus": "in_corpus.mp4"}

    usable, orphans = collect_frames(tmp_path, corpus)

    assert [p.name for p in usable] == ["in_corpus.f0000.jpg", "in_corpus.f0001.jpg"]
    assert orphans == 5


def test_group_hits_keeps_best_moment_per_video(tmp_path: Path) -> None:
    hits = [
        ("vid_a.f0002", 0.10),
        ("vid_a.f0009", 0.40),
        ("vid_b.f0001", 0.90),
        ("notavideo.f0003", 0.99),
    ]
    # per-video sampling density: vid_b frames land every 4s, vid_a every 10s
    seconds_for = {"vid_a.f0002": 20.0, "vid_a.f0009": 90.0, "vid_b.f0001": 4.0}

    grouped = group_hits(hits, top_k=5, seconds_for=seconds_for, corpus={"vid_a", "vid_b"})

    assert ("vid_b", 0.90, 4.0) in grouped
    assert ("vid_a", 0.40, 90.0) in grouped
    assert grouped[0][0] == "vid_b"


def test_frame_timestamp_parses_or_rejects() -> None:
    assert frame_timestamp("vid.f0012", 10.0) == 120.0
    assert frame_timestamp("vid.f0000", 5.0) == 0.0
    assert frame_timestamp("vid.jpg", 10.0) is None


def test_sampling_timestamps_spread_over_duration() -> None:
    assert sampling_timestamps(100.0, 4, 10.0) == [0.0, 25.0, 50.0, 75.0]


def test_sampling_timestamps_clamps_last_seek() -> None:
    # seeking to/past the final frame fails on several ffmpeg builds
    stamps = sampling_timestamps(0.1, 12, 10.0)
    assert all(s <= 0.05 for s in stamps)
    assert stamps[-1] == 0.05


def test_sampling_timestamps_falls_back_without_duration() -> None:
    assert sampling_timestamps(0.0, 3, 10.0) == [0.0, 10.0, 20.0]
    assert sampling_timestamps(0.0, 0, 5.0) == [0.0]
    assert sampling_timestamps(50.0, 0, 7.0) == [0.0]


def test_seconds_for_frames_mirrors_sampling_math(tmp_path: Path) -> None:
    frames = _make_frames(tmp_path, "a", 2) + _make_frames(tmp_path, "b", 2)

    seconds = seconds_for_frames(frames, {"a": 100.0}, count=4, fallback_interval=10.0)

    assert seconds["a.f0000"] == 0.0 and seconds["a.f0001"] == 25.0
    # no known duration -> fallback interval spacing
    assert seconds["b.f0001"] == 10.0


def test_reported_bug_sequence_index_then_search_stays_consistent(tmp_path: Path) -> None:
    """Regression for 'indexes then claims nothing indexed': after a sampling
    batch lands on disk, collection must immediately see the new frames."""
    videos = {"DJI_20240626161128_0051_D": "x/DJI_20240626161128_0051_D.MP4"}
    frames_root = tmp_path / "_search"

    first = plan_sampling(videos, frames_root)
    assert len(first.todo) == 1

    _make_frames(frames_root, "DJI_20240626161128_0051_D", 4)

    second = plan_sampling(videos, frames_root)
    assert second.todo == [] and second.covered_count == 1

    usable, orphans = collect_frames(frames_root, videos)
    assert len(usable) == 4 and orphans == 0

    hits = [(p.stem, 0.5 - 0.01 * int(p.stem.rsplit(".f", 1)[1])) for p in usable]
    seconds_for = {p.stem: float(p.stem.rsplit(".f", 1)[1]) * 2.0 for p in usable}
    grouped = group_hits(hits, top_k=5, seconds_for=seconds_for, corpus=set(videos))
    assert grouped and grouped[0][0] == "DJI_20240626161128_0051_D"
    best_key = max(usable, key=lambda p: -float(p.stem.rsplit(".f", 1)[1]) * 0.01)
    assert grouped[0][2] == seconds_for[best_key.stem]
