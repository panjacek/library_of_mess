import streamlit as st

from helpers.common import filter_db, load_db, update_db

st.set_page_config(page_title="Library of Mess - Tagging", page_icon="📚", layout="wide")

load_db()
db = st.session_state.db
filtered_db = filter_db()

edited_db = st.data_editor(filtered_db)
if st.button("Save Updates?"):
    update_db(edited_db)
show_video = st.selectbox("Show Video", sorted(filtered_db["path"]))
if show_video:
    # FIXME: HEVC H265 is not supported :/
    # TODO: check if video is HEVC
    # TODO: short or thumbnail:
    #       there seems to be play limit but still loads full video
    #       see https://github.com/streamlit/streamlit/issues/946
    with open(show_video, "rb") as video_file:
        st.video(video_file)
