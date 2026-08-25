import streamlit as st

from library_of_mess.database import update_edits
from library_of_mess.ui.helpers import ensure_db_loaded, render_filters, save_db, show_video_file

st.set_page_config(page_title="Library of Mess - Tagging", page_icon="📚", layout="wide")

db = ensure_db_loaded()
filtered_db = render_filters(db)

edited_db = st.data_editor(filtered_db)
if st.button("Save Updates?"):
    save_db(update_edits(db, edited_db))
    st.success("DB updated")
show_video = st.selectbox("Show Video", sorted(filtered_db["path"]), index=None)

if show_video:
    show_video_file(show_video)
