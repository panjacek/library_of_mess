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

test:  ## unit + UI smoke tests
	uv run pytest

run:  ## launch streamlit UI (http://localhost:8501)
	uv run streamlit run src/library_of_mess/ui/app.py

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

.PHONY: help sync format lint test run docker-build up stop shell clean
