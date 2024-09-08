import datetime
import logging
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.logger import get_logger

from helpers.common import (
    DB_COLUMNS,
    DB_PATH,
    LIBRARY_PATH,
    check_columns_in_db,
    create_entry_from_path,
    load_db,
)

logger = get_logger(__name__)


st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")


def parse_video_paths(list_of_videos) -> pd.DataFrame:
    """Convert list of video paths to dataframe"""
    data = [create_entry_from_path(video) for video in list_of_videos]
    logger.info(f"Found {len(data)} videos in library folders")
    st.write(f"Found {len(data)} videos in library folders")
    return pd.DataFrame(data, columns=DB_COLUMNS.keys())


def refresh_db(db_df: pd.DataFrame) -> pd.DataFrame:
    """Scan library folder and update DB"""
    video_files = Path(LIBRARY_PATH).glob("**/*.MP4")

    # Scan folder section
    st.subheader("Scan library folder")
    if st.button("Choose Folder"):
        folders = sorted(Path(LIBRARY_PATH).iterdir(), reverse=True)
        chosen_folders = st.multiselect("Folders", folders)

        if len(chosen_folders) == 1:
            st.write(chosen_folders[0])
            video_files = Path(chosen_folders[0]).glob("**/*.MP4")
            st.write(video_files)

    video_df = parse_video_paths(video_files)
    # compare DBs
    for index, row in video_df.iterrows():
        # add new video if not present if main db
        if row["path"] not in db_df["path"].values:
            db_df.loc[len(db_df.index)] = row
        else:
            # update video if present
            # Insert new columns here
            # db_df.loc[db_df["path"] == row["path"], "hyperlapse"] = row["hyperlapse"]
            # TODO: compare metadata and update if new tags or something was added to file

            # check if datetime is set, autoset based on file modified date
            if db_df.loc[db_df["path"] == row["path"]].datetime.values[0] is None:
                # get the file modified date from path
                modified_date = Path(row["path"]).stat().st_mtime
                db_df.loc[db_df["path"] == row["path"], "datetime"] = (
                    datetime.datetime.fromtimestamp(modified_date)
                )
                logger.debug(f"Set datetime for {row['path']} to {modified_date}")
    return db_df


# Init DB if not present
load_db(force_init=True)
if st.session_state.db is None:
    st.warning(f"No videos found in {DB_PATH}, create new one?")
    st.session_state.db = pd.DataFrame(columns=DB_COLUMNS)

# Init DB
if st.checkbox("I KNOW WHAT I DO....") is False:
    st.stop()

check_columns_in_db(fill_blanks=True)

if st.checkbox("Show raw DB"):
    st.write(st.session_state.db)

db = st.session_state.db

# Save current state of DB, use for refreshing columns
if st.button("Update DB - store current state"):
    st.session_state.db.to_parquet(DB_PATH)
    st.success("DB updated")

if st.button("Refresh DB - rescan"):
    db = refresh_db(db)
    db.to_parquet(DB_PATH)
