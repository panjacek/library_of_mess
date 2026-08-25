"""Scanning the library folder and building database entries."""

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mutagen
import pandas as pd
from streamlit.logger import get_logger

from library_of_mess.config import library_dir

logger = get_logger(__name__)

VIDEO_SUFFIXES = {".mp4", ".mov"}

DB_COLUMNS: dict[str, tuple[type, Any]] = {
    "path": (str, ""),
    "name": (str, ""),
    "tags": (str, ""),
    "year": (str, ""),
    "datetime": (datetime.datetime, None),
    "length": (float, 0.0),
    "bike": (bool, False),
    "hyperlapse": (bool, False),
}
# these are only generated, do not edit them
DB_COLUMNS_RO = ["path", "name", "length"]


@dataclass
class Entry:
    path: str
    name: str
    year: str
    datetime: datetime.datetime
    length: float
    bike: bool
    hyperlapse: bool
    tags: str


def to_relative(entry_path: Path) -> str:
    """Store paths relative to the library root so the DB survives relocations."""
    try:
        return entry_path.relative_to(library_dir()).as_posix()
    except ValueError:
        return str(entry_path)


def create_entry_from_path(entry_path: Path) -> Entry | None:
    """Build a database entry; None when the file is not recognizable media."""
    media_info = mutagen.File(entry_path)
    if media_info is None:
        logger.warning(f"Skipping unrecognized file {entry_path}")
        return None
    logger.debug(f"Len={media_info.info.length}s, {entry_path}")

    return Entry(
        path=to_relative(entry_path),
        name=entry_path.stem,
        year=DB_COLUMNS["year"][1],
        # get datetime based on file created timestamp
        datetime=datetime.datetime.fromtimestamp(entry_path.stat().st_mtime),
        length=round(media_info.info.length, 0),
        tags=DB_COLUMNS["tags"][1],
        bike=DB_COLUMNS["bike"][1],
        hyperlapse=DB_COLUMNS["hyperlapse"][1],
    )


def find_videos(folder: Path) -> list[Path]:
    """All video files below folder."""
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES)


def parse_video_paths(list_of_videos: list[Path]) -> pd.DataFrame:
    """Convert list of video paths to dataframe, skipping unparseable files."""
    entries = [create_entry_from_path(video) for video in list_of_videos]
    data = [entry for entry in entries if entry is not None]
    logger.info(f"Found {len(data)} videos")
    return pd.DataFrame(data, columns=list(DB_COLUMNS.keys()))


def refresh_db(db_df: pd.DataFrame, folders: list[Path] | None = None) -> tuple[pd.DataFrame, dict[str, int]]:
    """Rescan library folders: add new videos, backfill missing datetimes.

    Returns (dataframe, stats) where stats counts "added" and "skipped" files.
    """
    roots = folders if folders else [library_dir()]
    videos: list[Path] = []
    for root in roots:
        videos.extend(find_videos(root))

    before = len(db_df)
    scanned = parse_video_paths(videos)
    for _, row in scanned.iterrows():
        if row["path"] not in db_df["path"].values:
            db_df.loc[len(db_df.index)] = row
        else:
            mask = db_df["path"] == row["path"]
            if pd.isna(db_df.loc[mask, "datetime"].values[0]):
                db_df.loc[mask, "datetime"] = row["datetime"]
    stats = {"added": len(db_df) - before, "skipped": len(videos) - len(scanned)}
    return db_df, stats
