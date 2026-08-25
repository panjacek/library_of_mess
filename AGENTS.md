# AGENTS.md

Commands for working in this repo. Package lives in `src/library_of_mess`,
Streamlit UI in `src/library_of_mess/ui`.

## Commands

- `make sync` — install all deps (uv-managed, py3.14)
- `make test` — pytest unit + AppTest smoke tests
- `make lint` — ruff check/format + mypy + bandit
- `make format` — ruff autofix + reformat
- `make run` — streamlit app on :8501

Single test: `uv run pytest tests/test_database.py -q`

## Conventions

- Python 3.14, uv lockfile is source of truth — add deps via `uv add`
- Logic modules are pure (df-in/df-out); no `st.*` calls outside `ui/`
- All paths via `config.py` functions reading env at call time — never hardcode paths
- Tests are isolated from real data by `tests/conftest.py` autouse fixture; do not weaken it
- Line length 120; mypy strict-ish (no untyped defs); keep both green with `make lint`

## Gotchas

- pandas 3.x runtime — mind copy-on-write semantics in dataframe edits
- `pages/` numbering matters to streamlit discovery (002_, 003_, ...)
- thumbnail tests need ffmpeg binary; they skip silently without it (CI has it)
- shared checkout across machines: set `UV_PROJECT_ENVIRONMENT` outside the repo,
  else `.venv` symlinks break and uv rebuilds on every command
- python pinned exact (3.14.3) via `.python-version`; uv fetches it automatically
