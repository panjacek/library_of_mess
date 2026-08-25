"""Pure helpers behind the moment-search page (no streamlit — fully testable).

Frame files live in one flat directory as ``{video_stem}.f{idx:04d}.jpg``.
Everything here works on those names so the UI stays thin and the indexing
pipeline can be reasoned about (and regression-tested) without streamlit.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SamplingPlan:
    """What needs sampling vs what is already covered."""

    todo: list[str] = field(default_factory=list)
    covered: set[str] = field(default_factory=set)
    duplicate_stems: list[str] = field(default_factory=list)

    @property
    def covered_count(self) -> int:
        return len(self.covered)


logger = logging.getLogger(__name__)


def plan_sampling(videos: dict[str, str], frames_root: Path) -> SamplingPlan:
    """Split the corpus into already-sampled vs to-sample, detecting hazards."""
    frame_names = [p.name for p in frames_root.glob("*.f*.jpg")]
    covered_from_disk = {n.rsplit(".f", 1)[0] for n in frame_names}

    seen_stems: dict[str, int] = {}
    for stem in videos:
        seen_stems[stem] = seen_stems.get(stem, 0) + 1
    duplicates = sorted(s for s, c in seen_stems.items() if c > 1)
    for stem in duplicates:
        # same stem in multiple folders collides inside the shared flat frame
        # directory: one video's frames silently serve all of them
        logger.warning("duplicate video stem across folders: %s (%dx)", stem, seen_stems[stem])

    return SamplingPlan(
        todo=sorted(stem for stem in videos if stem not in covered_from_disk),
        covered={stem for stem in videos if stem in covered_from_disk},
        duplicate_stems=duplicates,
    )


def collect_frames(frames_root: Path, videos: dict[str, str]) -> tuple[list[Path], int]:
    """Return (frame paths belonging to the corpus, count of orphan frames).

    Orphans = frames on disk whose video is not in the current corpus
    (deleted files, narrowed name filter) — ignored, never embedded.
    """
    usable: list[Path] = []
    orphans = 0
    for p in frames_root.glob("*.f*.jpg"):
        if p.name.rsplit(".f", 1)[0] in videos:
            usable.append(p)
        else:
            orphans += 1
    return sorted(usable), orphans


def group_hits(
    hits: list[tuple[str, float]],
    top_k: int,
    seconds_for: dict[str, float],
    corpus: set[str] | None = None,
) -> list[tuple[str, float, float]]:
    """Collapse per-frame (key, score) hits to the best moment per video.

    `seconds_for` maps every frame key to its playback timestamp — this keeps
    timestamp math out of filenames even when sampling density varies per
    video. When `corpus` is given, hits for videos outside it are dropped.
    """
    best: dict[str, tuple[float, str]] = {}
    for key, score in hits:
        video, sep, _ = key.rpartition(".f")
        if not sep or not video:
            continue
        if corpus is not None and video not in corpus:
            continue
        known = best.get(video)
        if known is None or score > known[0]:
            best[video] = (score, key)
    ranked = sorted(best.items(), key=lambda item: -item[1][0])[:top_k]
    return [(video, score, seconds_for.get(key, 0.0)) for video, (score, key) in ranked]


def sampling_timestamps(duration: float, count: int, fallback_interval: float) -> list[float]:
    """Timestamps spreading `count` samples evenly across a video's duration.

    Non-positive durations fall back to `fallback_interval` spacing. Seeks are
    clamped just short of the end — several ffmpeg builds fail on the final frame.
    """
    count = max(count, 1)
    if duration <= 0:
        return [i * fallback_interval for i in range(count)]
    last_seekable = max(duration - 0.05, 0.0)
    return [min(i * duration / count, last_seekable) for i in range(count)]


def seconds_for_frames(
    frames: list[Path], durations: dict[str, float], count: int, fallback_interval: float
) -> dict[str, float]:
    """Frame key ('{stem}.f{idx}') -> playback seconds, mirroring sampling_timestamps math."""
    out: dict[str, float] = {}
    step_count = max(count, 1)
    for frame in frames:
        video, sep, idx = frame.stem.rpartition(".f")
        if not sep or not idx.isdigit():
            continue
        duration = durations.get(video, 0.0)
        step = duration / step_count if duration > 0 else fallback_interval
        out[frame.stem] = int(idx) * step
    return out


def frame_timestamp(frame_key: str, interval: float) -> float | None:
    """'{stem}.f{idx}' -> seconds, or None when the name is not a frame key."""
    _, sep, idx_part = frame_key.rpartition(".f")
    if not sep or not idx_part.isdigit():
        return None
    return int(idx_part) * interval
