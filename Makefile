help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

sync:  ## install/sync all deps (incl. dev group) into .venv
	uv sync --group dev

format:  ## auto-format code
	uv run ruff format .
	uv run ruff check --fix .

lint:  ## linters: ruff + mypy + bandit
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests
	uv run bandit -c pyproject.toml -r src -q

test:  ## unit + UI smoke tests, with coverage report
	uv run pytest --cov --cov-branch --cov-report=term-missing:skip-covered --cov-report=xml

run:  ## launch streamlit UI (http://localhost:8501)
	uv run streamlit run src/library_of_mess/ui/app.py

# throwaway playground, never touches your real library.parquet.
# Override location: make demo DEMO_DIR=/tmp/my-playground
DEMO_DIR ?= .cache/demo
DEMO_ENV := LIBRARY_DIR=$(DEMO_DIR)/library LIBRARY_DB=$(DEMO_DIR)/library.parquet THUMBNAILS_DIR=$(DEMO_DIR)/thumbnails EMBEDDINGS_PATH=$(DEMO_DIR)/embeddings.npz

# real file target: clips are generated once; `make clean` resets them
$(DEMO_DIR)/library.parquet:
	$(DEMO_ENV) uv run python scripts/make_demo_data.py

demo: $(DEMO_DIR)/library.parquet  ## run UI on throwaway demo db (generated on first use)
	$(DEMO_ENV) uv run streamlit run src/library_of_mess/ui/app.py

demo-reset:  ## delete demo playground so next `make demo` regenerates it
	rm -rf $(DEMO_DIR)

demo-data:  ## generate demo library into the isolated playground, no UI (needs ffmpeg)
	$(DEMO_ENV) uv run python scripts/make_demo_data.py

docker-build:  ## build the container image
	docker compose build

up:  ## start container in background
	docker compose up -d

stop:  ## stop containers
	docker compose down -t2

shell:  ## shell inside container
	docker compose run --rm -it library_of_mess /bin/bash

clean:  ## clean caches
	rm -rf ./.cache .pytest_cache .mypy_cache .ruff_cache

.PHONY: help sync format lint test run demo demo-reset demo-data docker-build up stop shell clean
