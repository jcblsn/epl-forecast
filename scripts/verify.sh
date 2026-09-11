#!/bin/sh
# Single verify entrypoint. Order matters: format before check, so that
# layout-only findings are fixed rather than aborting the run.
set -e

uv run ruff format .
uv run ruff check .
uv run pytest "$@"
