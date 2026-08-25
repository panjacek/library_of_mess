from pathlib import Path

import pytest

from library_of_mess import config


def test_defaults_resolve_relative(isolated_env: Path) -> None:
    assert config.library_dir() == isolated_env / "library"
    assert config.db_path() == isolated_env / "library.parquet"
    assert config.thumbnails_dir() == isolated_env / "thumbs"


def test_env_overrides(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIBRARY_DIR", "/data/media")
    monkeypatch.setenv("LIBRARY_DB", "/data/db.parquet")
    monkeypatch.setenv("THUMBNAILS_DIR", "/data/thumbs")

    assert str(config.library_dir()) == "/data/media"
    assert str(config.db_path()) == "/data/db.parquet"
    assert str(config.thumbnails_dir()) == "/data/thumbs"
