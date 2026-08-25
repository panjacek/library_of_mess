"""Parquet database: load, save, filter and merge edits."""

from pathlib import Path, PurePosixPath

import pandas as pd

from library_of_mess.config import library_dir
from library_of_mess.scanner import DB_COLUMNS, DB_COLUMNS_RO


def resolve_media_path(path_str: str | Path) -> Path:
    """Resolve a stored (library-relative or absolute) path to a real file."""
    path = Path(path_str)
    return path if path.is_absolute() else library_dir() / path


def migrate_legacy_paths(db_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Rewrite legacy absolute paths (e.g. docker-era /app/library/...) to
    library-relative ones by finding the longest tail that exists on disk.

    Rows whose file cannot be located are left untouched. Returns (df, fixed).
    """
    lib = library_dir()
    fixed = 0
    for idx in db_df.index:
        raw = str(db_df.at[idx, "path"])
        if not raw.startswith("/"):
            continue
        parts = PurePosixPath(raw).parts
        for start in range(len(parts)):
            candidate = Path(*parts[start:])
            if (lib / candidate).exists():
                db_df.at[idx, "path"] = candidate.as_posix()
                fixed += 1
                break
    return db_df, fixed


def empty_db() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DB_COLUMNS.keys()))


def load_db(db_file: Path | str) -> pd.DataFrame | None:
    """Load the parquet DB, None when it does not exist yet."""
    if not Path(db_file).exists():
        return None
    return pd.read_parquet(db_file)


def save_db(db_df: pd.DataFrame, db_file: Path | str) -> None:
    db_df.to_parquet(db_file)


def check_columns_in_db(db_df: pd.DataFrame, fill_blanks: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """Ensure all schema columns exist; optionally backfill missing ones.

    Returns (dataframe, list of missing column names).
    """
    missing = [col for col in DB_COLUMNS if col not in db_df.columns]
    if fill_blanks:
        for col in missing:
            db_df[col] = DB_COLUMNS[col][1]
        if "datetime" in missing:
            # None backfill yields object dtype; .dt accessors need datetime64
            db_df["datetime"] = pd.to_datetime(db_df["datetime"])
    return db_df, missing


DB_EDITABLE_COLUMNS = [c for c in DB_COLUMNS if c not in DB_COLUMNS_RO]


def update_edits(db_df: pd.DataFrame, edited_db: pd.DataFrame) -> pd.DataFrame:
    """Copy user-editable columns from an edited dataframe into the main DB.

    Rows are aligned by dataframe index (st.data_editor preserves it).
    """
    for idx, row in edited_db.iterrows():
        if idx not in db_df.index:
            continue
        for col in DB_EDITABLE_COLUMNS:
            if col in edited_db.columns:
                db_df.loc[idx, col] = row[col]
    return db_df


def filter_db(
    db_df: pd.DataFrame,
    name_filter: str = "",
    tags_filter: str = "",
    hide_nonbikes: bool = False,
    hide_bikes: bool = False,
    show_hyperlapse: bool = False,
    length_range: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """Apply filters, returns filtered dataframe."""
    filtered_db = db_df[db_df["path"].str.contains(name_filter)]
    if tags_filter:
        filtered_db = filtered_db[filtered_db["tags"].str.contains(tags_filter)]
    if hide_nonbikes:
        filtered_db = filtered_db[filtered_db["bike"]]  # noqa: E712
    if hide_bikes:
        filtered_db = filtered_db[~filtered_db["bike"]]
    if show_hyperlapse:
        filtered_db = filtered_db[filtered_db["hyperlapse"]]  # noqa: E712
    if length_range is not None:
        low, high = length_range
        filtered_db = filtered_db[(filtered_db["length"] >= low) & (filtered_db["length"] <= high)]
    return filtered_db
