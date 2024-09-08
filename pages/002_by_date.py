import streamlit as st

from helpers.common import filter_db, load_db, show_video_file

st.set_page_config(page_title="Library of Mess - tabbed", page_icon="📚", layout="wide")

load_db()
filtered_db = filter_db()

# Selected Year/Month
selector = ["year", "month", "day", "weekday"]

selector_choice = st.selectbox(
    "Group by", options=selector, index=selector.index("year")
)

# get unique values sorted
selected_values = filtered_db.datetime.dt.__getattribute__(selector_choice).unique()
selected_values.sort()

show_video_refs = {k: None for k in selected_values}

st.title(f"Videos by {selector_choice} of creation")
for selected_value in selected_values:
    with st.expander(str(selected_value)):
        # get all values where selector_choice value is used to show only speficic datetime objects
        # if year is selected show only entries where x.dataframe.year == selected_value
        st.write(f"{selector_choice} = {selected_value}")

        grouped_db = filtered_db[
            filtered_db.datetime.dt.__getattribute__(selector_choice) == selected_value
        ]
        if st.checkbox(f"Show raw DB for {selected_value}"):
            st.write(grouped_db)

        # Selection per group, ensure index is None to avoid mem crash
        show_video_refs[selected_value] = st.selectbox(
            "Show Video", sorted(grouped_db["path"]), index=None
        )

        if show_video_refs[selected_value]:
            show_video_file(show_video_refs[selected_value])


