import streamlit as st

from library_of_mess.ui.helpers import ensure_db_loaded, render_filters, show_video_file

st.set_page_config(page_title="Library of Mess - tabbed", page_icon="📚", layout="wide")

db = ensure_db_loaded()
filtered_db = render_filters(db)

if "datetime" not in filtered_db.columns:
    st.error("Database is missing the 'datetime' column — migrate schema on the Manage DB page")
    st.stop()

# Selected Year/Month
selector = ["year", "month", "day", "weekday"]

selector_choice = st.selectbox("Group by", options=selector, index=selector.index("year"))

# get unique values sorted
selected_values = filtered_db.datetime.dt.__getattribute__(selector_choice).unique()
selected_values.sort()

show_video_refs = {k: None for k in selected_values}

st.title(f"Videos by {selector_choice} of creation")
for selected_value in selected_values:
    with st.expander(str(selected_value)):
        st.write(f"{selector_choice} = {selected_value}")

        grouped_db = filtered_db[filtered_db.datetime.dt.__getattribute__(selector_choice) == selected_value]
        if st.checkbox(f"Show raw DB for {selected_value}"):
            st.write(grouped_db)

        # Selection per group, ensure index is None to avoid mem crash
        show_video_refs[selected_value] = st.selectbox("Show Video", sorted(grouped_db["path"]), index=None)

        if show_video_refs[selected_value]:
            show_video_file(show_video_refs[selected_value])
