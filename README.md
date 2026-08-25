# Library of Mess

Browse and tag your personal video library: a Streamlit UI over a parquet
metadata database. Built for drone/GoPro-style folders full of `MP4` clips —
filter by name, tags, length, bike/hyperlapse flags; watch inline; tag in a
spreadsheet view; browse thumbnails.

[![CI](https://github.com/panjacek/library_of_mess/actions/workflows/ci.yml/badge.svg)](https://github.com/panjacek/library_of_mess/actions/workflows/ci.yml)

## Why

Years of cycling clips in folders named `GoPro/2023/...` and zero idea what is
where. Existing gallery tools want to manage my photos too, so this became a
deliberately small, boring-stack alternative: **parquet as the database,
ffmpeg for frames, Streamlit for the UI** — one `uv sync` and you are running.
The long-term goal (see [Roadmap](#roadmap)) is tagging *by content*, not just
by hand.

## Features

- **Browse** — name/tag/length filters, inline playback (`st.video`), graceful HEVC fallback to thumbnails
- **By date** — group videos by year / month / day / weekday of creation
- **Tagging** — editable grid (year, tags, bike, hyperlapse) persisted to parquet
- **Gallery** — ffmpeg-generated thumbnail wall with pagination, negative-cache for undecodable files
- **Manage DB** — init/rescan library folder, schema migration for new columns

## Quick start — no media needed

One command: generates a synthetic demo library (tiny lavfi-generated clips)
and runs the UI against a **throwaway database** — your real data is never
read or written:

```bash
make sync    # uv only; Python 3.14 fetched automatically
make demo    # needs the ffmpeg binary; http://localhost:8501
```

The playground lives under `.cache/demo`; relocate it with
`make demo DEMO_DIR=/tmp/playground`, wipe it with `make demo-reset`.

## Using your own library

Point the app at your media root, then open **Manage DB**, accept the
"I know what I do" gate and rescan:

```bash
export LIBRARY_DIR=/path/to/your/videos
make run
```

## Configuration

| env var          | default               | description                    |
|------------------|-----------------------|--------------------------------|
| `LIBRARY_DIR`    | `./library`           | media library root             |
| `LIBRARY_DB`     | `./library.parquet`   | metadata database location     |
| `THUMBNAILS_DIR` | `./.cache/thumbnails` | thumbnail cache                |
| `THUMBNAIL_WORKERS` | `4`                   | parallel ffmpeg processes      |
| `EMBEDDINGS_PATH` | `./.cache/embeddings.npz` | embedding store (semantic search groundwork) |

## Docker

```bash
export LIBRARY_PATH=/path/to/your/videos   # compose-only var: media mount (read-only)
export PORT=8000
make docker-build && make up
```

Note the naming: `LIBRARY_PATH` is interpolated by docker-compose for the
media mount; inside the container the app reads `LIBRARY_DIR=/library`. The
database lives in a named docker volume (`mess-data`), media is never written.

## Make targets

Run `make help`. The essentials:

- `make demo` — try it instantly on a throwaway demo library
- `make run` — streamlit UI on :8501
- `make test` — unit + per-page AppTest smoke tests
- `make lint` — ruff + mypy + bandit
- `make format` — ruff auto-format
- `make sync` — install/sync deps into `.venv`
- `make docker-build && make up` — containerized, port from `$PORT`

## Development

Layout, data flow, DB schema and the test-isolation story:
[`docs/architecture.md`](docs/architecture.md). CI pipeline:
[`docs/ci.md`](docs/ci.md).

Tests never touch your real database — they run against throwaway fixtures in
tmp dirs, enforced by an autouse pytest fixture.

```bash
make test   # thumbnail tests skip when no local ffmpeg
```

**Sharing the checkout between machines?** A `.venv` contains absolute-path
symlinks, so it is machine-local. Point uv at a private environment and it
never travels with the repo:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/library_of_mess"   # ~/.bashrc
rm -rf .venv && make sync   # once, then never think about it again
```

## Troubleshooting

**`PermissionError: [Errno 13] Permission denied: 'library.parquet'`**
The database was created by an older docker setup running as root, so your
user cannot write it. Take ownership once:

```bash
sudo chown $USER:$USER library.parquet
sudo chown -R $USER:$USER .cache
```

## Roadmap

The original vision: tagging **by content**, not just by hand —

- scene embeddings (CLIP-style) → "find clips that look like X".
  Groundwork is merged (`embeddings.py`: incremental thumbnail-keyed cache,
  cosine ranking, model-agnostic encoder interface). Model/runtime research is
  ongoing — torch-based CLIP works today but drags ~2.5GB into a 464MB project,
  so lighter backends (ONNX runtime, distilled models) are being evaluated first
- audio transcription → searchable spoken-content tags
- duplicate/near-duplicate detection across folders

## License

Unlicense — see [LICENSE](LICENSE).
