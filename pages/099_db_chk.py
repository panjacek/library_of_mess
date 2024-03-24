import logging
from pathlib import Path

import mutagen
import pandas as pd
import streamlit as st

from helpers.common import DB_COLUMNS, DB_PATH, LIBRARY_PATH, load_db

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")


def parse_video_paths(list_of_videos) -> pd.DataFrame:
    """Convert list of video paths to dataframe"""
    video_dict = {k: [] for k in DB_COLUMNS}
    for video_path in list_of_videos:
        video_dict["path"].append(str(video_path))
        video_dict["name"].append(video_path.stem)
        video_dict["year"].append("")

        # parse metadata is super slow..
        mutagen_info = mutagen.File(video_path)
        logger.debug(f"Len={mutagen_info.info.length}s, {video_path}")

        video_dict["length"].append(round(mutagen_info.info.length, 0))

        # generic tags
        video_dict["tags"].append("")
        # more specific importat tags
        video_dict["bike"].append(False)
        video_dict["hyperlapse"].append(False)

    st.write(f"Found {len(video_dict['path'])} videos in library folders")
    return pd.DataFrame(data=video_dict)


def refresh_db(db_df):
    video_files = Path(LIBRARY_PATH).glob("**/*.MP4")
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
            pass
            # update video if present
            # Insert new columns here
            # db_df.loc[db_df["path"] == row["path"], "hyperlapse"] = row["hyperlapse"]
            # TODO: compare metadata and update if new tags or something was added to file
    return db_df


# Init DB if not present
load_db(force_init=True)
db = st.session_state.db
if db is None:
    st.warning(f"No videos found in {DB_PATH}, create new one?")
    db = pd.DataFrame(columns=DB_COLUMNS)

# Init DB
if st.checkbox("I KNOW WHAT I DO....") is False:
    st.stop()

if st.checkbox("Show raw DB"):
    st.write(db)

if st.button("Refresh DB"):
    db = refresh_db(db)
    db.to_parquet(DB_PATH)
