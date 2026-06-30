#!/bin/sh
# Container entrypoint: apply DB schema, then start the API server.
# `set -e` aborts immediately if any command fails (e.g. migrations error),
# so we never start the server against a half-migrated database.
set -e

echo "==> Applying database migrations (alembic upgrade head)"
alembic upgrade head

echo "==> Starting API server on :8000"
# `exec` replaces this shell with uvicorn so it becomes PID 1 and receives
# Docker's stop signals directly (clean, fast shutdowns).
# NOTE: no --reload here — that's a dev-only feature. We run a fixed worker count.
exec uvicorn summary_generator.main:app --host 0.0.0.0 --port 8000 --workers 2
