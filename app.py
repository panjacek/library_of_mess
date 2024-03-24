import logging
from pathlib import Path

import mutagen
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")

logger = logging.getLogger(__name__)

LIBRARY_PATH = "/app/library"
DB_PATH = "/app/library.db"
DB_COLUMNS = ["path", "name", "year", "tags", "length", "bike", "hyperlapse"]
# these are only generated, do not edit them
DB_COLUMNS_RO = ["path", "name", "length"]
MIME_TO_CHECK = ["video/mp4"]


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
    if st.button("Choose Folder"):
        folders = sorted(Path(LIBRARY_PATH).iterdir(), reverse=True)
        chosen_folders = st.multiselect("Folders", folders)

        if len(chosen_folders) == 1:
            st.write(chosen_folders[0])
            video_files = Path(chosen_folders[0]).glob("**/*.MP4")
            st.write(video_files)
    else:
        video_files = Path(LIBRARY_PATH).glob("**/*.MP4")

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

st.title("Library of Mess")

# Init DB if not present
db = None
if Path(DB_PATH).exists():
    db = pd.read_parquet(DB_PATH)
else:
    db = pd.DataFrame(columns=DB_COLUMNS)

# Init DB
if st.button("Refresh DB"):
    db = refresh_db(db)
    db.to_parquet(DB_PATH)

if st.checkbox("Show raw DB"):
    st.write(db)

name_filter = st.text_input("Filter by name", "")
tags_filter = st.text_input("Filter by tags", "")
filtered_db = db[db["path"].str.contains(name_filter)]
if tags_filter:
    filtered_db = filtered_db[filtered_db["tags"].str.contains(tags_filter)]

if st.checkbox("Hide nonbikes"):
    filtered_db = filtered_db[filtered_db["bike"] == True]  # noqa: E712

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
    (filtered_db["length"] >= len_filter[0]) & (filtered_db["length"] <= len_filter[1])
]

if st.checkbox("Show Video"):
    edited_db = st.data_editor(filtered_db)
    if st.button("Save Updates?"):
        for index, row in edited_db.iterrows():
            db.loc[db["path"] == row["path"], "year"] = row["year"]
            db.loc[db["path"] == row["path"], "tags"] = row["tags"]
            db.loc[db["path"] == row["path"], "bike"] = row["bike"]
            db.loc[db["path"] == row["path"], "hyperlapse"] = row["hyperlapse"]
        db.to_parquet(DB_PATH)
    show_video = st.selectbox("Show Video", sorted(filtered_db["path"]))
    if show_video:
        # FIXME: HEVC H265 is not supported :/
        # TODO: check if video is HEVC
        # TODO: short or thumbnail:
        #       there seems to be play limit but still loads full video
        #       see https://github.com/streamlit/streamlit/issues/946
        with open(show_video, "rb") as video_file:
            st.video(video_file)
