FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# ffmpeg powers thumbnail generation in the gallery page
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# non-root on purpose: containers must not spawn root-owned files in volumes
RUN useradd --create-home --uid 1000 mess \
    && mkdir -p /data \
    && chown mess:mess /data

USER mess
WORKDIR /app

# deps first: this layer is cached until the lockfile changes
COPY --chown=mess:mess pyproject.toml uv.lock README.md ./
COPY --chown=mess:mess src ./src
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=mess:mess src ./src
COPY --chown=mess:mess .streamlit ./.streamlit
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"]

CMD ["streamlit", "run", "src/library_of_mess/ui/app.py", "--server.address=0.0.0.0"]
