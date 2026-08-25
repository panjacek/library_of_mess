import pandas as pd
from pathlib import Path

from library_of_mess import config, database


def test_load_db_missing_returns_none() -> None:
    assert database.load_db(config.db_path()) is None


def test_save_load_roundtrip(sample_df: pd.DataFrame) -> None:
    database.save_db(sample_df, config.db_path())
    loaded = database.load_db(config.db_path())
    assert loaded is not None
    pd.testing.assert_frame_equal(loaded, sample_df)


def test_check_columns_backfills(sample_df: pd.DataFrame) -> None:
    df = sample_df.drop(columns=["tags", "bike"])
    fixed, missing = database.check_columns_in_db(df, fill_blanks=True)
    assert missing == ["tags", "bike"]
    assert (fixed["tags"] == "").all()
    assert not fixed["bike"].any()


def test_check_columns_report_only(sample_df: pd.DataFrame) -> None:
    df = sample_df.drop(columns=["year"])
    _, missing = database.check_columns_in_db(df, fill_blanks=False)
    assert missing == ["year"]


def test_filter_by_name(sample_df: pd.DataFrame) -> None:
    out = database.filter_db(sample_df, name_filter="a_ride")
    assert list(out["name"]) == ["a_ride"]


def test_filter_by_tags(sample_df: pd.DataFrame) -> None:
    out = database.filter_db(sample_df, tags_filter="winter")
    assert list(out["name"]) == ["c_jump"]


def test_filter_flags(sample_df: pd.DataFrame) -> None:
    assert sorted(database.filter_db(sample_df, hide_nonbikes=True)["name"]) == [
        "a_ride",
        "c_jump",
    ]
    assert sorted(database.filter_db(sample_df, hide_bikes=True)["name"]) == ["b_walk"]
    assert sorted(database.filter_db(sample_df, show_hyperlapse=True)["name"]) == ["c_jump"]


def test_filter_length_range(sample_df: pd.DataFrame) -> None:
    out = database.filter_db(sample_df, length_range=(50.0, 400.0))
    assert sorted(out["name"]) == ["b_walk", "c_jump"]


def test_update_edits_touches_editable_columns_only(sample_df: pd.DataFrame) -> None:
    edited = sample_df.copy()
    edited.loc[edited.index[0], "tags"] = "new_tag"
    original = sample_df.copy()

    merged = database.update_edits(original, edited)

    assert merged.iloc[0]["tags"] == "new_tag"


def test_update_edits_ignores_unknown_index(sample_df: pd.DataFrame) -> None:
    edited = sample_df.copy()
    edited.index = edited.index + 100

    merged = database.update_edits(sample_df.copy(), edited)

    assert (merged["tags"] == sample_df["tags"]).all()


def test_backfilled_datetime_is_datetime64(sample_df: pd.DataFrame) -> None:
    df = sample_df.drop(columns=["datetime"])

    fixed, missing = database.check_columns_in_db(df, fill_blanks=True)

    assert missing == ["datetime"]
    assert str(fixed["datetime"].dtype).startswith("datetime64")


def test_resolve_media_path(isolated_env: Path) -> None:
    assert database.resolve_media_path("2010/a.mp4") == isolated_env / "library" / "2010" / "a.mp4"
    assert database.resolve_media_path("/abs/a.mp4").as_posix() == "/abs/a.mp4"


def test_migrate_legacy_paths(sample_df: pd.DataFrame, isolated_env: Path) -> None:
    legacy_dir = isolated_env / "library" / "2010"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "MOV1.mp4").write_bytes(b"\x00")

    df = sample_df.copy()
    df["path"] = ["/app/library/2010/MOV1.mp4", "/app/library/lost/X.mp4", "/app/library/b_walk.mp4"]
    (isolated_env / "library" / "b_walk.mp4").write_bytes(b"\x00")

    out, fixed = database.migrate_legacy_paths(df)

    assert fixed == 2
    assert out.iloc[0]["path"] == "2010/MOV1.mp4"
    assert out.iloc[1]["path"] == "/app/library/lost/X.mp4"  # unfindable stays
    assert out.iloc[2]["path"] == "b_walk.mp4"
