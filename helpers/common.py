from pathlib import Path

import pandas as pd
import streamlit as st

LIBRARY_PATH = "/app/library"
DB_PATH = "/app/library.db"
DB_COLUMNS = ["path", "name", "year", "tags", "length", "bike", "hyperlapse"]
# these are only generated, do not edit them
DB_COLUMNS_RO = ["path", "name", "length"]


def load_db(force_init=False, force_reload=False) -> pd.DataFrame:
    if st.session_state.get("db") is not None and not force_reload:
        return

    if Path(DB_PATH).exists():
        st.session_state["db"] = pd.read_parquet(DB_PATH)
    elif force_init:
        st.session_state["db"] = pd.DataFrame(columns=DB_COLUMNS)
    else:
        st.warning("Go to db creation page")
        st.stop()


def update_db(edited_db: pd.DataFrame) -> None:
    db = st.session_state["db"]
    for index, row in edited_db.iterrows():
        db.loc[db["path"] == row["path"], "year"] = row["year"]
        db.loc[db["path"] == row["path"], "tags"] = row["tags"]
        db.loc[db["path"] == row["path"], "bike"] = row["bike"]
        db.loc[db["path"] == row["path"], "hyperlapse"] = row["hyperlapse"]
    db.to_parquet(DB_PATH)


def filter_db() -> pd.DataFrame:
    """Apply various filters returns filtered dataframe"""
    db = st.session_state.db
    name_filter = st.text_input("Filter by name", "")
    tags_filter = st.text_input("Filter by tags", "")
    filtered_db = db[db["path"].str.contains(name_filter)]
    if tags_filter:
        filtered_db = filtered_db[filtered_db["tags"].str.contains(tags_filter)]

    if st.checkbox("Hide nonbikes"):
        filtered_db = filtered_db[filtered_db["bike"] == True]  # noqa: E712
    if st.checkbox("Show Hyperlapse"):
        filtered_db = filtered_db[filtered_db["hyperlapse"] == True]  # noqa: E712

    if filtered_db.empty:
        st.write("No videos found")
        st.stop()

    # Cut long/short
    len_filter = st.slider(
        "Length",
        min_value=filtered_db["length"].min(),
        max_value=filtered_db["length"].max(),
        value=(filtered_db["length"].min(), filtered_db["length"].max()),
    )
    filtered_db = filtered_db[
        (filtered_db["length"] >= len_filter[0])
        & (filtered_db["length"] <= len_filter[1])
    ]
    return filtered_db
