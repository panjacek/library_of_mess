"""Thumbnail generation via ffmpeg."""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ffmpeg
import pandas as pd
from streamlit.logger import get_logger

from library_of_mess.config import thumbnails_dir, thumbnail_workers

logger = get_logger(__name__)

THUMBNAIL_WIDTH = 400


def generate_thumbnail(in_filename: str | Path, out_filename: str | Path, time: float, width: int) -> None:
    """Extract single frame of video and save it as image.

    Args:
        in_filename: Path to video file
        out_filename: Path to output image
        time: Time in seconds
        width: Width of thumbnail

    """
    try:
        (
            ffmpeg.input(in_filename, ss=time)
            .filter("scale", width, -1)
            .output(out_filename, vframes=1, threads=1)
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as ffmpeg_err:
        stderr_tail = ffmpeg_err.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["?"]
        logger.warning(f"ffmpeg failed on {in_filename}: {stderr_tail[0]}")
        raise ffmpeg_err


def thumbnail_path_for(video_path: Path, output_dir: Path) -> Path:
    return output_dir / (video_path.stem + ".jpg")


def failure_marker_for(video_path: Path, output_dir: Path) -> Path:
    """Marker file written when ffmpeg cannot decode a video (negative cache)."""
    return output_dir / (video_path.stem + ".jpg.fail")


def clear_failure_markers(output_dir: Path | None = None) -> int:
    """Delete all failure markers so failed videos get retried. Returns count."""
    output_dir = output_dir if output_dir is not None else thumbnails_dir()
    removed = 0
    if not output_dir.exists():
        return 0
    for marker in output_dir.glob("*.jpg.fail"):
        marker.unlink(missing_ok=True)
        removed += 1
    logger.info(f"Cleared {removed} thumbnail failure markers")
    return removed


def generate_thumbnail_from_video(video_path: Path, output_dir: Path) -> dict:
    """Extract first frame of video into output_dir (cached by filename).

    Thread-safe; races on directory creation and duplicate stems resolve
    harmlessly because ffmpeg overwrites the same target.

    Returns dict with "path" (video) and "thumbnail" (image) keys.
    Raises ffmpeg.Error when the video cannot be decoded.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    thumb = thumbnail_path_for(video_path, output_dir)
    if thumb.exists():
        logger.debug(f"Thumbnail {thumb} already exists")
    else:
        logger.debug(f"Extracting first frame of {video_path}")
        generate_thumbnail(str(video_path), str(thumb), 0, THUMBNAIL_WIDTH)

    return {"path": video_path, "thumbnail": thumb}


def generate_thumbnails(
    paths: Iterable[str | Path],
    output_dir: Path | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Generate thumbnails for many videos in parallel.

    Decode failures (ffmpeg.Error) get a marker file and are not retried until
    markers are cleared. Missing files (FileNotFoundError) count as skipped but
    leave no marker — they are often transient (unmounted drive).

    Args:
        paths: video paths to thumbnail
        output_dir: cache dir, defaults to configured thumbnails dir
        max_workers: parallel ffmpeg processes, defaults to configured workers
        progress_callback: optional callable(done_count, total_count)

    Returns (dataframe of path/thumbnail, number of skipped videos).
    """
    output_dir = output_dir if output_dir is not None else thumbnails_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    max_workers = max_workers if max_workers is not None else thumbnail_workers()
    path_list = [Path(p) for p in paths]

    generated: list[dict] = []
    skipped = 0
    pending: list[Path] = []
    for video_path in path_list:
        if failure_marker_for(video_path, output_dir).exists():
            skipped += 1
        elif thumbnail_path_for(video_path, output_dir).exists():
            # cached hit without spawning ffmpeg
            generated.append({"path": video_path, "thumbnail": thumbnail_path_for(video_path, output_dir)})
        else:
            pending.append(video_path)
    if progress_callback:
        progress_callback(len(path_list) - len(pending), len(path_list))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(generate_thumbnail_from_video, p, output_dir): p for p in pending}
        done = len(path_list) - len(pending)
        for future in as_completed(futures):
            video_path = futures[future]
            done += 1
            if progress_callback:
                progress_callback(done, len(path_list))
            try:
                generated.append(future.result())
            except ffmpeg.Error:
                skipped += 1
                failure_marker_for(video_path, output_dir).write_text("")
            except FileNotFoundError:
                # transient (missing file / unmounted drive): retry next time
                skipped += 1

    return pd.DataFrame(generated), skipped
