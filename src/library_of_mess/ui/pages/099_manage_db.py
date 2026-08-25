import streamlit as st
from streamlit.logger import get_logger

from library_of_mess import config, database
from library_of_mess.database import check_columns_in_db, empty_db
from library_of_mess.scanner import refresh_db
from library_of_mess.ui.helpers import save_db

st.set_page_config(page_title="Library of Mess - Manage DB", page_icon="📚", layout="wide")

logger = get_logger(__name__)

# This page must work without an existing database: load raw, bootstrap empty.
db = database.load_db(config.db_path())
if db is None:
    db = empty_db()

if st.checkbox("I KNOW WHAT I DO....") is False:
    st.stop()

db, missing = check_columns_in_db(db, fill_blanks=True)
for col in missing:
    st.warning(f"Backfilled missing column {col}")

if st.checkbox("Show raw DB"):
    st.write(db)

# Save current state of DB, use for refreshing columns
if st.button("Update DB - store current state"):
    save_db(db)
    st.success("DB updated")

st.subheader("Scan library folder")
st.caption(
    f"Scanner looks inside {config.library_dir()} — subfolders appear in the picker. "
    "Empty selection scans the whole library."
)
library_root = config.library_dir()
available_folders = sorted(library_root.iterdir(), reverse=True) if library_root.exists() else []
folders_choice = st.multiselect("Folders", available_folders)
if st.button("Refresh DB - rescan"):
    db, stats = refresh_db(db, folders=folders_choice or None)
    save_db(db)
    if stats["added"]:
        st.success(f"Added {stats['added']} new videos, {stats['skipped']} unreadable skipped — total {len(db)}")
    else:
        st.info(
            f"No new videos found ({len(db)} already known, {stats['skipped']} unreadable skipped). "
            "New media must be a video format (mp4/mov) under the library folder."
        )
