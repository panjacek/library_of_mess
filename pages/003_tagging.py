import streamlit as st

from helpers.common import filter_db, load_db, show_video_file, update_db

st.set_page_config(
    page_title="Library of Mess - Tagging", page_icon="📚", layout="wide"
)

load_db()
db = st.session_state.db
filtered_db = filter_db()

edited_db = st.data_editor(filtered_db)
if st.button("Save Updates?"):
    update_db(edited_db)
show_video = st.selectbox("Show Video", sorted(filtered_db["path"]), index=None)

if show_video:
    show_video_file(show_video)
