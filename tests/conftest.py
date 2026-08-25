"""Test fixtures.

Isolation guarantee: an autouse fixture chdirs into tmp_path and points every
config env var there, so the real library.parquet can never be touched.
"""

import datetime
import subprocess
import shutil
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from library_of_mess.scanner import DB_COLUMNS

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("LIBRARY_DB", str(tmp_path / "library.parquet"))
    monkeypatch.setenv("THUMBNAILS_DIR", str(tmp_path / "thumbs"))
    yield tmp_path


@pytest.fixture
def sample_df(isolated_env: Path) -> pd.DataFrame:
    """Three entries living inside the isolated library dir."""
    lib = isolated_env / "library"
    lib.mkdir(parents=True, exist_ok=True)
    rows = [
        ("a_ride.mp4", "summer", 10.0, True, False),
        ("b_walk.mp4", "", 60.0, False, False),
        ("c_jump.mp4", "summer,winter", 300.0, True, True),
    ]
    records = []
    for i, (name, tags, length, bike, hyperlapse) in enumerate(rows):
        video = lib / name
        video.write_bytes(b"\x00")
        records.append(
            {
                "path": video.name,  # stored library-relative
                "name": video.stem,
                "tags": tags,
                "year": "",
                "datetime": datetime.datetime(2024, i + 1, 15, 12, 0, 0),
                "length": length,
                "bike": bike,
                "hyperlapse": hyperlapse,
            }
        )
    return pd.DataFrame(records, columns=list(DB_COLUMNS.keys()))


@pytest.fixture
def seeded_db(sample_df: pd.DataFrame) -> Path:
    """Sample dataframe persisted as the (test) database."""
    from library_of_mess import config, database

    database.save_db(sample_df, config.db_path())
    return config.db_path()


@pytest.fixture
def tiny_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Real playable mp4 via ffmpeg lavfi testsrc; skipped without ffmpeg."""
    if not FFMPEG:
        pytest.skip("ffmpeg binary not available")
    out = tmp_path_factory.mktemp("videos") / "tiny.mp4"
    subprocess.run(
        [FFMPEG, "-f", "lavfi", "-i", "testsrc=duration=1:size=128x72:rate=2", "-y", str(out)],
        capture_output=True,
        check=True,
    )
    return out
