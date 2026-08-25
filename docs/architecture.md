# Architecture

Single-language Python app: a Streamlit UI on top of a parquet metadata database.
Logic lives in an importable package (`src/library_of_mess`), Streamlit glue is
confined to the `ui/` subpackage.

## Data flow

```
                scan (mutagen: length, mtime)
media files ──────────────────────► scanner.py ──► library.parquet
(LIBRARY_DIR)                                        │
                                                     │ load_db()
                                                     ▼
              filter (name/tags/bike/length)   database.py ◄── edit/tag (data_editor)
                                                     │
                                                     ▼
                                               ui/pages/*.py ──► streamlit UI
                                                     │
                              thumbnails (ffmpeg)    │ show video / gallery
                                     ▲               ▼
                                thumbnails.py     st.video / st.image
```

## Package layout

```
src/library_of_mess/
├── config.py       # env-driven paths, read at call time (LIBRARY_DIR/LIBRARY_DB/THUMBNAILS_DIR)
├── scanner.py      # Entry dataclass, folder scan, refresh/merge logic, DB schema
├── database.py     # load/save parquet, filters, column checks, edit merge
├── thumbnails.py   # ffmpeg frame extraction with filename cache
├── paginator.py    # streamlit pagination helper
└── ui/
    ├── app.py            # browse page (streamlit entrypoint)
    ├── helpers.py        # session-state glue, shared filter widgets
    └── pages/
        ├── 002_by_date.py     # group videos by year/month/day/weekday
        ├── 003_tagging.py     # spreadsheet-style tagging (data_editor)
        ├── 004_gallery.py     # thumbnail gallery
        └── 099_manage_db.py   # init/rescan/persist database
```

Multipage discovery works because `pages/` sits next to `app.py`; run with
`make run` → `uv run streamlit run src/library_of_mess/ui/app.py`.

## Database schema

Parquet file (despite the historical `.db` name), one row per video:

| column     | type       | editable | notes                          |
|------------|------------|----------|--------------------------------|
| path       | str        | no       | absolute path, primary key     |
| name       | str        | no       | file stem                      |
| length     | float      | no       | seconds, from mutagen          |
| datetime   | datetime64 | auto     | file mtime, backfillable       |
| tags       | str        | yes      | free-form, comma separated     |
| year       | str        | yes      | manual                         |
| bike       | bool       | yes      | domain tag                     |
| hyperlapse | bool       | yes      | domain tag                     |

Schema lives in `scanner.DB_COLUMNS`; missing columns are detected at load and
can be backfilled from the Manage DB page.

## Configuration

| env var          | default               | set by docker-compose to |
|------------------|-----------------------|--------------------------|
| `LIBRARY_DIR`    | `./library`           | `/library` (ro mount)    |
| `LIBRARY_DB`     | `./library.parquet`   | `/data/library.parquet`  |
| `THUMBNAILS_DIR` | `./.cache/thumbnails` | `/data/thumbs`           |
| `THUMBNAIL_WORKERS` | `4`                   | (host only) parallel ffmpeg |

Paths are resolved inside functions, never at import time — this is what lets
tests redirect everything into pytest tmp dirs.

## Test isolation

`tests/conftest.py` installs an autouse fixture that chdirs into `tmp_path`
and points all three config vars there. The real database is unreachable from
tests even if code tries to touch it; UI pages are smoke-tested headlessly via
`streamlit.testing.v1.AppTest`. Thumbnail tests need an ffmpeg binary and skip
otherwise (CI installs one).
