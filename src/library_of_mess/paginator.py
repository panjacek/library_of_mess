"""Based on example from https://gist.github.com/treuille/2ce0acb6697f205e44e3e0f576e810b7"""

import itertools
from collections.abc import Iterable, Iterator
from typing import Any

import streamlit as st


def page_format_func(i: int) -> str:
    return f"Page {i}"


def paginator(
    label: str, items: Iterable[Any], items_per_page: int = 10, on_sidebar: bool = True
) -> Iterator[tuple[int, Any]]:
    """Lets the user paginate a set of items.

    Yields only the items on the selected page, including the item's index.
    """
    if on_sidebar:
        location = st.sidebar.empty()
    else:
        location = st.empty()

    items = list(items)
    n_pages = (len(items) - 1) // items_per_page + 1
    page_number = location.selectbox(label, range(n_pages), format_func=page_format_func)

    min_index = page_number * items_per_page
    max_index = min_index + items_per_page
    return itertools.islice(enumerate(items), min_index, max_index)
