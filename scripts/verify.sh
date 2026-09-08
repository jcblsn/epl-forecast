#!/bin/sh
# Single verify entrypoint. Order matters: format before check, so that
# layout-only findings are fixed rather than aborting the run.
# --all-extras keeps the research extra installed; a plain `uv sync` prunes it
# and the numpyro tests silently turn into skips.
set -e

uv run --all-extras ruff format .
uv run --all-extras ruff check .
uv run --all-extras pytest "$@"
