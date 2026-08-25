import streamlit as st

from library_of_mess.ui.helpers import (
    ensure_db_loaded,
    render_filters,
    show_video_file,
    warm_embedding_model,
)

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")

st.title("Library of Mess")

# load the embedding model in the background so first search is fast
warm_embedding_model()

db = ensure_db_loaded()

filtered_db = render_filters(db)

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

# semantic-search results can request playback directly (seek to moment)
play_now = st.session_state.pop("play_video", None)
start_at = st.session_state.pop("play_video_start", None)
if play_now:
    show_video_file(play_now, start_time=int(start_at) if start_at is not None else None)
elif show_video:
    show_video_file(show_video, partial_path=partial_path, filtered_db=filtered_db)
