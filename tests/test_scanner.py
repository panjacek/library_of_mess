import datetime
from pathlib import Path

import pandas as pd
import pytest

import library_of_mess.scanner as scanner
from library_of_mess import config
from library_of_mess.scanner import create_entry_from_path, find_videos, refresh_db


class FakeInfo:
    length = 42.0


class FakeFile:
    info = FakeInfo()


def patch_mutagen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scanner.mutagen, "File", lambda p: FakeFile())


def test_find_videos_suffix_filter(tmp_path: Path) -> None:
    (tmp_path / "x.MP4").write_bytes(b"")
    (tmp_path / "y.mp4").write_bytes(b"")
    (tmp_path / "z.mov").write_bytes(b"")
    (tmp_path / "n.txt").write_bytes(b"")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.mp4").write_bytes(b"")

    found = [p.name for p in find_videos(tmp_path)]

    assert found == ["deep.mp4", "x.MP4", "y.mp4", "z.mov"]


def test_refresh_db_adds_new_video(
    sample_df: pd.DataFrame, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_mutagen(monkeypatch)
    db = sample_df.copy()
    size_before = len(db)
    new_video = config.library_dir() / "d_new.mp4"
    new_video.touch()

    refreshed, stats = refresh_db(db)

    assert len(refreshed) == size_before + 1
    assert (refreshed["name"] == "d_new").any()
    assert stats["added"] == 1


def test_refresh_db_keeps_existing(sample_df: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mutagen(monkeypatch)
    db = sample_df.copy()

    refreshed, stats = refresh_db(db)

    assert len(refreshed) == len(db)
    assert stats["added"] == 0


def test_refresh_db_backfills_nat_datetime(
    sample_df: pd.DataFrame, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_mutagen(monkeypatch)
    db = sample_df.copy()
    known_path = db.loc[db.index[0], "path"]
    db.loc[db.index[0], "datetime"] = pd.NaT

    out, _ = refresh_db(db)

    assert out.loc[out["path"] == known_path, "datetime"].notna().all()


def test_create_entry_from_path(tiny_video: Path) -> None:
    entry = create_entry_from_path(tiny_video)
    assert entry is not None

    assert entry.name == "tiny"
    assert 0 < entry.length <= 2
    assert entry.tags == ""
    assert isinstance(entry.datetime, datetime.datetime)


def test_parse_video_paths_skips_unparseable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    garbage = tmp_path / "broken.mp4"
    garbage.write_bytes(b"\x00not-a-video")

    df = scanner.parse_video_paths([garbage])

    assert len(df) == 0


def test_entry_path_stored_relative(tmp_path: Path, isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_mutagen(monkeypatch)
    nested = config.library_dir() / "2010" / "trip"
    nested.mkdir(parents=True)
    video = nested / "MOV1.MP4"
    video.write_bytes(b"\x00")

    entry = scanner.create_entry_from_path(video)

    assert entry is not None
    assert entry.path == "2010/trip/MOV1.MP4"
