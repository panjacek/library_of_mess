"""Streamlit glue: session-state DB loading and widgets shared across pages."""

from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.logger import get_logger

from library_of_mess import config, database
from library_of_mess import thumbnails as thumbs

logger = get_logger(__name__)

# st.video crashes on HEVC/H265 in most browsers/codecs; show thumbnail instead
UNSUPPORTED_CODECS = {"hevc", "h265"}


def ensure_db_loaded(force_reload: bool = False) -> pd.DataFrame:
    """Load the parquet DB into session state once; stops the page when missing."""
    if st.session_state.get("db") is None or force_reload:
        db_file = config.db_path()
        db_df = database.load_db(db_file)
        if db_df is None:
            st.warning(f"No database found at {db_file}")
            st.page_link("pages/099_manage_db.py", label="Open Manage DB to create one", icon="🗂️")
            st.stop()

        # one-time fixup for databases created with absolute (docker-era) paths
        if db_df["path"].astype(str).str.startswith("/").any():
            db_df, migrated = database.migrate_legacy_paths(db_df)
            if migrated:
                database.save_db(db_df, db_file)
                st.info(f"Migrated {migrated} legacy paths to be library-relative")

        _, missing = database.check_columns_in_db(db_df)
        for col in missing:
            st.warning(f"Column {col} not found in DB")
        st.session_state.db = db_df
    db: pd.DataFrame = st.session_state.db
    return db


def save_db(df: pd.DataFrame) -> None:
    """Persist session dataframe and keep session state in sync."""
    database.save_db(df, config.db_path())
    st.session_state.db = df


def render_filters(db_df: pd.DataFrame) -> pd.DataFrame:
    """Filter widgets used by every page, returns filtered dataframe."""
    name_filter = st.text_input("Filter by name", "")
    tags_filter = st.text_input("Filter by tags", "")
    hide_nonbikes = st.checkbox("Hide nonbikes")
    hide_bikes = st.checkbox("Hide bikes")
    show_hyperlapse = st.checkbox("Show Hyperlapse")

    filtered_db = database.filter_db(
        db_df,
        name_filter=name_filter,
        tags_filter=tags_filter,
        hide_nonbikes=hide_nonbikes,
        hide_bikes=hide_bikes,
        show_hyperlapse=show_hyperlapse,
    )

    if filtered_db.empty:
        st.write("No videos found")
        st.stop()

    # Cut long/short
    low, high = float(filtered_db["length"].min()), float(filtered_db["length"].max())
    if low < high:
        length_range = st.slider("Length", min_value=low, max_value=high, value=(low, high))
        return database.filter_db(filtered_db, length_range=length_range)
    return filtered_db


def _cached_codec(resolved: Path) -> str | None:
    """video_codec with a session cache — streamlit reruns pages on every
    widget interaction, so probing would otherwise spawn ffprobe per render."""
    cache: dict[str, str | None] = st.session_state.setdefault("codec_cache", {})
    key = str(resolved)
    if key not in cache:
        cache[key] = thumbs.video_codec(resolved)
    return cache[key]


def show_video_file(
    video_path: str | Path, partial_path: bool = False, filtered_db: pd.DataFrame | None = None
) -> None:
    """Show video file using streamlit.video.

    Falls back to the cached thumbnail with a warning for codecs st.video
    cannot render (HEVC/H265).
    """
    if partial_path:
        # find this name in filtered_db, potential issue if 2 same names
        if filtered_db is None:
            raise ValueError("filtered_db is required when partial_path is set")
        match = filtered_db.loc[filtered_db["name"] == video_path, "path"]
        stored = match.values[0]
    else:
        stored = video_path

    resolved = database.resolve_media_path(stored)
    codec = _cached_codec(resolved)
    if codec in UNSUPPORTED_CODECS:
        st.warning(f"Browser cannot play {codec.upper()} video — showing thumbnail instead")
        thumb = thumbs.thumbnail_path_for(resolved, config.thumbnails_dir())
        if thumb.exists():
            st.image(str(thumb))
        return

    st.video(resolved.read_bytes())
