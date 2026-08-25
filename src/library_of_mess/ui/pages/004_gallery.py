import streamlit as st
from streamlit.logger import get_logger

from library_of_mess.database import resolve_media_path
from library_of_mess.thumbnails import clear_failure_markers, generate_thumbnails
from library_of_mess.paginator import paginator
from library_of_mess.ui.helpers import ensure_db_loaded, render_filters

st.set_page_config(page_title="Library of Mess - Gallery", page_icon="📚", layout="wide")

logger = get_logger(__name__)

db = ensure_db_loaded()
filtered_db = render_filters(db)

# show/hide db
if st.checkbox("Show raw DB"):
    st.write(filtered_db)

if st.checkbox("Show thumbnails"):
    force_retry = st.button(
        "Force refresh failed thumbnails",
        help="Clears the remembered failures so skipped videos are retried",
    )
    if force_retry:
        cleared = clear_failure_markers()
        if cleared:
            st.info(f"Cleared {cleared} failure markers — retrying them on this page")

    all_paths = filtered_db["path"].astype(str).tolist()

    # paginate over videos FIRST: only the visible page gets thumbnailed,
    # cached thumbnails make later visits instant
    _, paths_on_page = map(list, zip(*paginator("Select Video page", all_paths, items_per_page=100)))

    progress = st.progress(0.0, text="Generating thumbnails...")

    def update_progress(done: int, count: int) -> None:
        progress.progress(done / count if count else 1.0, text=f"Thumbnails {done}/{count}")

    images_to_show, thumb_failures = generate_thumbnails(
        [str(resolve_media_path(p)) for p in paths_on_page],
        progress_callback=update_progress,
    )
    progress.empty()

    if thumb_failures:
        st.warning(
            f"{thumb_failures} videos on this page could not be thumbnailed "
            "(corrupt file or unsupported codec) — skipped and remembered"
        )

    if images_to_show.empty:
        st.write("No thumbnails could be generated on this page")
        st.stop()

    # keep page order stable across reruns
    page_order = {path: pos for pos, path in enumerate(paths_on_page)}
    images_to_show["_pos"] = images_to_show["path"].map(lambda p: page_order.get(str(p), len(page_order)))
    images_to_show = images_to_show.sort_values("_pos")
    images_to_show["name"] = images_to_show["path"].apply(lambda x: x.name)

    if st.checkbox("Show Only Names"):
        captions_to_show = images_to_show["name"].astype(str)
    else:
        captions_to_show = images_to_show["path"].astype(str)

    st.image(images_to_show["thumbnail"].astype(str).tolist(), caption=captions_to_show.to_list())
