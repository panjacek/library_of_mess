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
| `MODEL_CACHE_DIR` | `~/.cache/library_of_mess/models` | downloaded model weights (optional extra) |
| `EMBEDDINGS_DEVICE` | `cpu` | torch device for the encoder (`cuda` after installing CUDA wheels) |
| `EMBEDDINGS_MODEL` | `google/siglip2-base-patch16-224` | any pinned `google/siglip2-*`; switching rebuilds the store automatically. `base-patch32-256` = ~3× faster indexing, lower recall |
| `SEARCH_FRAMES_PER_VIDEO` | `12` | frames sampled per video, spaced evenly across its duration |
| `SEARCH_FRAME_INTERVAL` | `10` | fallback spacing when a video's duration is unknown |
| `SEARCH_INDEX_BUDGET` | `25` | max videos sampled per search-page visit (0 = search only what's indexed) |

## Semantic search (optional extra)

CLIP-style "find clips that look like X" runs **Google's SigLIP2-B/32 directly**
(`google/siglip2-base-patch32-256`, Apache-2.0) via transformers + PyTorch
(the `torch` package) on CPU — entirely local, no API, no converted artifacts.
Not installed by default:

```bash
uv sync --extra embeddings
```

First use downloads the checkpoint once (~1.1GB fp32, revision-pinned) into
`MODEL_CACHE_DIR`; thumbnails are embedded incrementally and cached in
`EMBEDDINGS_PATH`, so re-scans only encode new videos (~6 img/s indexing,
~0.2s per query on a modern laptop CPU). Video resolution is irrelevant to
search cost — embedding operates on 400px thumbnails, so a 4K library costs
the same as a 720p one.

GPU later: install torch CUDA wheels instead of the pinned CPU ones and set
`EMBEDDINGS_DEVICE=cuda`.

### Where downloads live

| content | location | lifetime |
|---|---|---|
| model weights (~1.1GB) | `MODEL_CACHE_DIR` → `~/.cache/library_of_mess/models` | permanent — never cleaned by the app; survives venv rebuilds, `make clean`, restarts; safe to back up |
| embedding store | `EMBEDDINGS_PATH` | grows with your library (~3KB/frame); delete to force re-embed |
| sampled frames | `.cache/thumbnails/_search/` | decode cache; delete to force re-sampling |

`make clean` only wipes repo-relative caches — home-directory model weights
are never touched. Contributors: the embedding stack is part of the default
dev environment, so `make test` always exercises it. On app start the model
loads in a background thread (`EMBEDDINGS_WARMUP=0` to disable), so the first
search is ready without a cold wait.

Without the extra, the app works as usual; the search page shows a hint
instead. Research and measurements: [docs/research/embedding-models.md](docs/research/embedding-models.md),
decision record: [docs/adr/0001-semantic-search-stack.md](docs/adr/0001-semantic-search-stack.md).

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

- scene embeddings (CLIP-style) → shipped as moment search: every video is
  sampled into frames (one per `SEARCH_FRAME_INTERVAL` seconds, default 10) and
  each frame is embedded, so a query like "rainy descent" returns the exact
  moment — with playback seeking straight to it. Runs the official Google
  SigLIP2-B/32 checkpoint via transformers/PyTorch CPU behind an optional
  `embeddings` extra (`uv sync --extra embeddings`); weights download once to a
  cache dir, base install stays light.
  Research and measurements: [docs/research/embedding-models.md](docs/research/embedding-models.md),
  decision record: [docs/adr/0001-semantic-search-stack.md](docs/adr/0001-semantic-search-stack.md)
- audio transcription → searchable spoken-content tags
- duplicate/near-duplicate detection across folders

## License

Unlicense — see [LICENSE](LICENSE).
