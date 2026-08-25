import streamlit as st

from library_of_mess.ui.helpers import ensure_db_loaded, render_filters, show_video_file

st.set_page_config(page_title="Library of Mess", page_icon="📚", layout="wide")

st.title("Library of Mess")

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

if show_video:
    show_video_file(show_video, partial_path=partial_path, filtered_db=filtered_db)
