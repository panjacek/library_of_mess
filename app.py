from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")

LIBRARY_PATH = "/app/library"
DB_PATH = "/app/library.db"
DB_COLUMNS = ["path", "name", "year", "tags"]


def parse_video_paths(list_of_videos) -> pd.DataFrame:
    """Convert list of video paths to dataframe"""
    video_dict = {k: [] for k in DB_COLUMNS}
    for video_path in list_of_videos:
        video_dict["path"].append(str(video_path))
        video_dict["name"].append(video_path.stem)
        video_dict["year"].append("")
        video_dict["tags"].append([])

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
    db_df = pd.concat([db_df, video_df], ignore_index=True).drop_duplicates(subset="path")
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

name_filter = st.text_input("Filter by name", "2024")
db = db[db["path"].str.contains(name_filter)]
if st.checkbox("Show DB"):
    st.write(db)

if st.checkbox("Show Video"):
    show_video = st.selectbox("Show Video", db["path"])
    if show_video:
        with open(show_video, "rb") as video_file:
            st.video(video_file.read())

# TODO: specific year/folder per tab
if False:
    st.session_state["tabs"] = []
    for folder in chosen_folders:
        if folder.is_dir():
            st.write(folder.basename)
            st.write(folder.glob("*.mp4"))
            st.session_state["tabs"].append(f"{folder.basename}")

    if st.button("Show"):
        tabs = st.tabs(st.session_state["tabs"])
