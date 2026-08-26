# sandbox and host share this checkout: per-user venv paths stop the two
# environments from invalidating each other's interpreter symlinks
export UV_PROJECT_ENVIRONMENT ?= $(CURDIR)/.venv-$(USER)

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

sync:  ## install/sync all deps (incl. dev group) into the per-user venv
	uv sync --group dev

sync-embeddings:  ## base deps + optional semantic-search stack (torch etc.)
	uv sync --group dev --extra embeddings

format:  ## auto-format code
	uv run --no-sync ruff format .
	uv run --no-sync ruff check --fix .

lint:  ## linters: ruff + mypy + bandit
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check .
	uv run --no-sync mypy src tests
	uv run --no-sync bandit -c pyproject.toml -r src -q

test:  ## unit + UI smoke tests, with coverage report
	uv run --no-sync pytest --cov --cov-branch --cov-report=term-missing:skip-covered --cov-report=xml

run:  ## launch streamlit UI (http://localhost:8501)
	uv run --no-sync streamlit run src/library_of_mess/ui/app.py

# throwaway playground, never touches your real library.parquet.
# Override location: make demo DEMO_DIR=/tmp/my-playground
# NOTE: playground lives under .cache/ — `make clean-cache` resets it.
DEMO_DIR ?= .cache/demo
DEMO_ENV := LIBRARY_DIR=$(DEMO_DIR)/library LIBRARY_DB=$(DEMO_DIR)/library.parquet THUMBNAILS_DIR=$(DEMO_DIR)/thumbnails EMBEDDINGS_PATH=$(DEMO_DIR)/embeddings.npz

# real file target: clips are generated once; `make clean-cache` resets them
$(DEMO_DIR)/library.parquet:
	$(DEMO_ENV) uv run --no-sync python scripts/make_demo_data.py

demo: $(DEMO_DIR)/library.parquet  ## run UI on throwaway demo db (generated on first use)
	$(DEMO_ENV) uv run streamlit run src/library_of_mess/ui/app.py

demo-reset:  ## delete demo playground so next `make demo` regenerates it
	rm -rf $(DEMO_DIR)

demo-data:  ## generate demo library into the isolated playground, no UI (needs ffmpeg)
	$(DEMO_ENV) uv run --no-sync python scripts/make_demo_data.py

# override knobs: make eval EVAL_ARGS="--filter 202608 --k 5"
eval:  ## retrieval-quality eval on the real library (needs eval_labels.json + embeddings extra)
	uv run --no-sync python scripts/eval_search.py $(EVAL_ARGS)

docker-build:  ## build the container image
	docker compose build

up:  ## start container in background
	docker compose up -d

stop:  ## stop containers
	docker compose down -t2

shell:  ## shell inside container
	docker compose run --rm -it library_of_mess /bin/bash

clean:  ## remove tool caches + coverage artifacts (cheap, always safe)
	rm -rf .pytest_cache .mypy_cache .ruff_cache coverage.xml .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

# GNU make convention: a ladder of clean targets, cheapest first.
clean-cache:  ## remove GENERATED caches: thumbnails, search frames, embeddings npz, eval CSVs, demo playground (hours of ffmpeg/CPU to rebuild!)
	rm -rf ./.cache

clean-models:  ## delete downloaded embedding model weights (~1.1GB; re-downloads on next run)
	rm -rf "${MODEL_CACHE_DIR:-$$HOME/.cache/library_of_mess/models}"

.PHONY: help sync sync-embeddings format lint test run demo demo-reset demo-data eval clean clean-cache clean-models docker-build up stop shell
