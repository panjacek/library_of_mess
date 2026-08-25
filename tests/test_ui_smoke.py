"""UI smoke tests via streamlit AppTest — run every page against the fixture DB."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "library_of_mess" / "ui"

PAGES = [
    "app.py",
    "pages/002_by_date.py",
    "pages/003_tagging.py",
    "pages/004_gallery.py",
    "pages/099_manage_db.py",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(seeded_db: Path, page: str) -> None:
    at = AppTest.from_file(str(UI_DIR / page), default_timeout=30)
    at.run()
    assert not at.exception


def test_missing_db_stops_browse_page(isolated_env: Path) -> None:
    at = AppTest.from_file(str(UI_DIR / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.warning) == 1


def test_name_filter_narrows_results(seeded_db: Path) -> None:
    at = AppTest.from_file(str(UI_DIR / "app.py"), default_timeout=30)
    at.run()
    at.text_input[0].set_value("a_ride").run()
    options = at.selectbox[0].options
    assert len(options) == 1 and "a_ride" in options[0]


def test_manage_db_bootstraps_without_database(isolated_env: Path) -> None:
    at = AppTest.from_file(str(UI_DIR / "pages" / "099_manage_db.py"), default_timeout=30)
    at.run()
    assert not at.exception

    at.checkbox[0].check().run()
    assert not at.exception
    assert len(at.button) > 0
