import datetime
from dataclasses import dataclass
from pathlib import Path

import mutagen
import pandas as pd
import streamlit as st
from streamlit.logger import get_logger

from helpers.ffmpeg import generate_thumbnail_from_video

logger = get_logger(__name__)


LIBRARY_PATH = "/app/library"
DB_PATH = "/app/library.db"
DB_COLUMNS = {
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


def create_entry_from_path(entry_path: Path) -> Entry:
    _mutagen_info = mutagen.File(entry_path)
    logger.debug(f"Len={_mutagen_info.info.length}s, {entry_path}")

    return Entry(
        path=str(entry_path),
        name=entry_path.stem,
        year=DB_COLUMNS["year"][1],
        # get datetime based on file created timestamp
        datetime=datetime.datetime.fromtimestamp(entry_path.stat().st_mtime),
        length=round(_mutagen_info.info.length, 0),
        tags=DB_COLUMNS["tags"][1],
        bike=DB_COLUMNS["bike"][1],
        hyperlapse=DB_COLUMNS["hyperlapse"][1],
    )


def check_columns_in_db(fill_blanks: bool = False) -> None:
    """Check if db got all columns, insert missing if fill_blanks is set to True"""
    db_df = st.session_state["db"]
    for column, column_defaults in DB_COLUMNS.items():
        if column not in db_df.columns:
            waning_msg = f"Column {column} not found in DB"
            logger.warning(waning_msg)
            st.warning(waning_msg)
            if fill_blanks:
                db_df[column] = column_defaults[1]


def load_db(force_init=False, force_reload=False) -> pd.DataFrame:
    if st.session_state.get("db") is not None and not force_reload:
        return

    if Path(DB_PATH).exists():
        st.session_state["db"] = pd.read_parquet(DB_PATH)
        check_columns_in_db()
    elif force_init:
        st.session_state["db"] = pd.DataFrame(columns=list(DB_COLUMNS.keys()))
    else:
        st.warning("Go to db creation page")
        st.stop()


def update_db(edited_db: pd.DataFrame) -> None:
    db = st.session_state["db"]
    for index, row in edited_db.iterrows():
        db.loc[db["path"] == row["path"], "year"] = row["year"]
        db.loc[db["path"] == row["path"], "tags"] = row["tags"]
        db.loc[db["path"] == row["path"], "bike"] = row["bike"]
        db.loc[db["path"] == row["path"], "hyperlapse"] = row["hyperlapse"]
    db.to_parquet(DB_PATH)


def filter_db() -> pd.DataFrame:
    """Apply various filters returns filtered dataframe"""
    db = st.session_state.db
    name_filter = st.text_input("Filter by name", "")
    tags_filter = st.text_input("Filter by tags", "")
    filtered_db = db[db["path"].str.contains(name_filter)]
    if tags_filter:
        filtered_db = filtered_db[filtered_db["tags"].str.contains(tags_filter)]

    if st.checkbox("Hide nonbikes"):
        filtered_db = filtered_db[filtered_db["bike"] == True]  # noqa: E712
    if st.checkbox("Hide bikes"):
        filtered_db = filtered_db[filtered_db["bike"] == False]  # noqa: E712
    if st.checkbox("Show Hyperlapse"):
        filtered_db = filtered_db[filtered_db["hyperlapse"] == True]  # noqa: E712

    if filtered_db.empty:
        st.write("No videos found")
        st.stop()

    # Cut long/short
    len_filter = st.slider(
        "Length",
        min_value=filtered_db["length"].min(),
        max_value=filtered_db["length"].max(),
        value=(filtered_db["length"].min(), filtered_db["length"].max()),
    )
    filtered_db = filtered_db[
        (filtered_db["length"] >= len_filter[0])
        & (filtered_db["length"] <= len_filter[1])
    ]
    return filtered_db


# FIXME: HEVC H265 is not supported :/
# TODO: check if video is HEVC to avoid crashes
# TODO: short or thumbnail:
#       there seems to be play limit but still loads full video eating a lot of ram
#       see https://github.com/streamlit/streamlit/issues/946
def show_video_file(
    video_path: Path, partial_path: bool = False, filtered_db: pd.DataFrame = None
) -> None:
    """Show video file using streamlit.video.

    Args:
        video_path (Path): Path to video file
        partial_path (bool, optional): If True, hide full path. Defaults to False.
        filtered_db (pd.DataFrame): Filtered dataframe, required if partial_path is True

    Returns:
        None
    """
    if partial_path:
        # find this name in filtered_db, potential issue if 2 same names
        video_path = filtered_db[filtered_db["name"] == video_path]["path"].values[0]
    with open(video_path, "rb") as video_file:
        st.video(video_file)


def generate_thumbnails(filtered_db: pd.DataFrame) -> list[Path]:
    """Show thumbnail of video using streamlit.image.

    Args:
        filtered_db (pd.DataFrame): Filtered dataframe

    Returns:
        list[Path]: List of thumbnail paths
    """
    output_dir = Path("/app/.cache/thumbnails/")
    generated_thumbnails = []

    for video_path in filtered_db["path"]:
        video_path = Path(video_path)
        generated_thumbnails.append(
            generate_thumbnail_from_video(video_path, output_dir)
        )

    return pd.DataFrame(generated_thumbnails)
