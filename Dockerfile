# syntax=docker/dockerfile:1

# =============================================================================
# STAGE 1 — "builder": install dependencies and bake in the embedding model.
# We do the heavy, slow work here. None of this stage's build tools end up in
# the final image — only the artifacts we explicitly copy out in stage 2.
# =============================================================================
FROM python:3.12-slim AS builder

# `uv` is the fast Python package manager this project already uses (uv.lock).
# We grab its prebuilt binary from the official uv image instead of pip-installing it.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE: precompile .pyc for faster container start.
# UV_LINK_MODE=copy:   avoid hardlink warnings across Docker layers.
# HF_HOME:             where HuggingFace/sentence-transformers caches the model.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# --- Dependency layer (cached) ------------------------------------------------
# Copy ONLY the dependency manifests first. As long as these files don't change,
# Docker reuses the cached install layer below, even when your app code changes.
# README.md is here because pyproject.toml references it as the package readme.
COPY pyproject.toml uv.lock README.md ./

# Install third-party deps only (not your project yet) into /app/.venv.
# --frozen: use the exact versions pinned in uv.lock (reproducible builds).
# --no-dev: skip pytest/ruff/etc — they don't belong in a runtime image.
RUN uv sync --frozen --no-dev --no-install-project

# --- Application layer --------------------------------------------------------
# Now copy the source and install the project itself into the venv.
COPY . .
RUN uv sync --frozen --no-dev

# --- Bake the embedding model into the image ---------------------------------
# At runtime the app runs OFFLINE (HF_HUB_OFFLINE=1 in embedder.py), so the
# model must already be on disk. We flip offline OFF here, just once, to pull
# all-MiniLM-L6-v2 (~90 MB) into HF_HOME so every container starts instantly
# with no network dependency on HuggingFace.
RUN HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 \
    .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"


# =============================================================================
# STAGE 2 — "runtime": the small, clean image we actually ship and run.
# It contains only the OS libs the app needs, the prebuilt venv, the model
# cache, and the source code — none of uv's build machinery.
# =============================================================================
FROM python:3.12-slim AS runtime

# PYTHONUNBUFFERED:      stream logs straight to stdout (so CloudWatch sees them).
# PYTHONDONTWRITEBYTECODE: don't litter .pyc files at runtime.
# HF_HOME:               point at the baked-in model cache from stage 1.
# PATH:                  put the venv first so `uvicorn`/`alembic`/`python` resolve to it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf-cache \
    PATH="/app/.venv/bin:$PATH"

# System libraries the Python packages link against at runtime:
#   libmagic1 -> python-magic (file-type sniffing during upload validation)
#   libgomp1  -> OpenMP runtime needed by torch / sentence-transformers
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user — if the app is ever compromised, the blast radius is smaller.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Copy the finished artifacts out of the builder. `--chown` makes them owned by
# our non-root user so it can read them.
COPY --from=builder --chown=app:app /app/.venv      /app/.venv
COPY --from=builder --chown=app:app /opt/hf-cache   /opt/hf-cache

# Copy the application source (the .dockerignore keeps junk like .venv/.git out).
COPY --chown=app:app . .

# The entrypoint runs DB migrations then launches the server. Make it executable.
RUN chmod +x /app/docker-entrypoint.sh

USER app
EXPOSE 8000

# Docker periodically calls /health so the orchestrator knows the container is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health').status==200 else sys.exit(1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
