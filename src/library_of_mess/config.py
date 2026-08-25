"""Runtime configuration: every path comes from the environment, read at call time.

Tests point these at tmp dirs, docker-compose points them at /library and
/data — the real database can never be reached by accident.
"""

import os
from pathlib import Path


def library_dir() -> Path:
    """Root of the media library (read-only usage)."""
    return Path(os.environ.get("LIBRARY_DIR", "./library"))


def db_path() -> Path:
    """Location of the parquet metadata database."""
    return Path(os.environ.get("LIBRARY_DB", "./library.parquet"))


def thumbnails_dir() -> Path:
    """Cache directory for generated thumbnails."""
    return Path(os.environ.get("THUMBNAILS_DIR", "./.cache/thumbnails"))


def embeddings_path() -> Path:
    """Location of the CLIP embedding store (npz)."""
    return Path(os.environ.get("EMBEDDINGS_PATH", "./.cache/embeddings.npz"))


def thumbnail_workers() -> int:
    """Parallel ffmpeg processes used for thumbnail batches."""
    return int(os.environ.get("THUMBNAIL_WORKERS", "4"))
