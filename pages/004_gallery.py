import streamlit as st
from streamlit.logger import get_logger

from helpers.common import filter_db, generate_thumbnails, load_db
from helpers.paginator import paginator

st.set_page_config(
    page_title="Library of Mess - Gallery", page_icon="📚", layout="wide"
)

logger = get_logger(__name__)

load_db()
db = st.session_state.db
if db is None:
    st.warning("No videos found, check your database")
    st.stop()

filtered_db = filter_db()

# show/hide db
if st.checkbox("Show raw DB"):
    st.write(filtered_db)

if st.checkbox("Show thumbnails"):
    images_to_show = generate_thumbnails(filtered_db)
    st.write(f"Found {len(images_to_show)} videos")

    images_to_show.name = images_to_show.path.apply(lambda x: x.name)

    thumbs_paginator = paginator(
        "Select Video to show",
        images_to_show.thumbnail.astype(str).tolist(),
        items_per_page=100,
    )

    # paginators
    indices_on_page, images_on_page = map(list, zip(*thumbs_paginator))

    # sliced paths to show
    if st.checkbox("Show Only Names"):
        # convert path to name
        captions_to_show = images_to_show.name.astype(str).iloc[indices_on_page]
    else:
        captions_to_show = images_to_show.path.astype(str).iloc[indices_on_page]

    # Show the gallery of thumbnails use video_path as caption
    st.image(images_on_page, caption=captions_to_show.to_list())
