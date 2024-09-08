import logging

import streamlit as st
from streamlit.logger import get_logger

from helpers.common import filter_db, load_db, show_video_file

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")

# add sublogger for page info
logger = get_logger(__name__)
logger.setLevel(logging.DEBUG)

st.title("Library of Mess")

load_db()
db = st.session_state.db
if db is None:
    st.warning("No videos found, check your database")
    st.stop()

filtered_db = filter_db()

# show/hide db
if st.checkbox("Show raw DB"):
    st.write(filtered_db)

# Dropdown select box, on mobile full path is too long
partial_path = False
if st.checkbox("Hide fullpath"):
    show_video = st.selectbox("Show Video", sorted(filtered_db["name"]), index=None)
    partial_path = True
else:
    show_video = st.selectbox("Show Video", sorted(filtered_db["path"]), index=None)

if show_video:
    show_video_file(show_video, partial_path=partial_path, filtered_db=filtered_db)
