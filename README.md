# Library of Mess

Browse and tag your personal video library by content: a Streamlit UI over a
parquet metadata database. Built for drone/GoPro-style folders full of `MP4`
clips — filter by name, tags, length, bike/hyperlapse flags; watch inline;
tag in a spreadsheet view; browse thumbnails.

[![CI](https://github.com/panjacek/library_of_mess/actions/workflows/ci.yml/badge.svg)](https://github.com/panjacek/library_of_mess/actions/workflows/ci.yml)

## Features

- **Browse** — name/tag/length filters, inline playback (`st.video`)
- **By date** — group videos by year / month / day / weekday of creation
- **Tagging** — editable grid (year, tags, bike, hyperlapse) persisted to parquet
- **Gallery** — ffmpeg-generated thumbnail wall with pagination
- **Manage DB** — init/rescan library folder, schema migration for new columns

## Quick start

[uv](https://docs.astral.sh/uv/) only, Python 3.14 is fetched automatically:

```bash
uv sync --group dev
make run        # http://localhost:8501
```

First run: open the **Manage DB** page, accept the "I know what I do" gate and
rescan your library folder (default `./library`, override with env vars below).

## Docker

```bash
export LIBRARY_PATH=/path/to/your/videos   # your media root (mounted read-only)
export PORT=8000
make docker-build && make up
```

The database lives in a named docker volume (`mess-data`), media is never
written to.

## Configuration

| env var          | default               | description                    |
|------------------|-----------------------|--------------------------------|
| `LIBRARY_DIR`    | `./library`           | media library root             |
| `LIBRARY_DB`     | `./library.parquet`   | metadata database location     |
| `THUMBNAILS_DIR` | `./.cache/thumbnails` | thumbnail cache                |
| `THUMBNAIL_WORKERS` | `4`                   | parallel ffmpeg processes      |

## Make targets

Run `make help`. The essentials:

- `make run` — streamlit UI on :8501
- `make test` — unit + per-page AppTest smoke tests
- `make lint` — ruff + mypy + bandit
- `make format` — ruff auto-format
- `make sync` — install/sync deps into `.venv`

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

- scene embeddings (CLIP-style) → "find clips that look like X"
- audio transcription → searchable spoken-content tags
- duplicate/near-duplicate detection across folders

## License

Unlicense — see [LICENSE](LICENSE).
