# Open Premier League forecast

A Python framework for reproducible Premier League forecasting experiments. The
first milestone ingests 16 seasons of Premier League and Championship results,
compares three chronological benchmarks, and simulates a season remainder.

The provisional baseline is a regularized team attack/defense Poisson model. It
improves on league-only benchmarks in the initial backtest and remains behind the
market comparison. A subsequent [Elo comparison](docs/experiments/E002.md) did not
meet the rule for replacing it. See [the initial experiment report](docs/experiments/E001.md),
[data inventory](docs/data_inventory.md), and [original design](docs/design_preliminary.md).

## Reproduce experiments

Run from the repository root with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run python scripts/reproduce.py --output runs/reproduction
```

This restores the pinned public downloads, checks two independent normalizations,
compares the 2024/25 results against OpenFootball, evaluates development/validation/
holdout splits, and runs 10,000 season simulations. Use a new output directory for
each run. It takes a few minutes; no API key is needed. Cached data allows all
forecasting and simulation work to run offline.

To reproduce the retrospective Elo comparison with the same simulation reference:

```sh
uv run python scripts/reproduce.py --config configs/elo.toml --output runs/elo-reproduction
```

The original E001 implementation is preserved in commit `6277385`. New source
changes produce a new code fingerprint; the E001 evidence retains its original
fingerprint. All E002 periods were already inspected in E001, including the period
named `holdout`, and are explicitly labeled retrospective.

Raw data stays in the ignored `data/raw/` directory. Each file is identified by its
SHA-256 hash. The committed [snapshot](configs/data_snapshot.json) records URLs,
original retrieval times and hashes. A changed upstream file causes restoration
to fail rather than silently altering an experiment. Keep the original raw cache
if you need long-term reproduction after a source correction.

## Individual commands

```sh
uv run epl-forecast data restore
uv run epl-forecast data normalize
uv run epl-forecast data audit
uv run epl-forecast data cross-check

uv run epl-forecast evaluate --split development --output runs/development
uv run epl-forecast evaluate --split validation --output runs/validation
uv run epl-forecast evaluate --split holdout --output runs/holdout

uv run epl-forecast predict --season 2024-2025 --date 2024-08-17 \
  --home arsenal --away wolverhampton-wanderers --output runs/match.json

uv run epl-forecast simulate --season 2024-2025 --as-of 2025-01-01 \
  --simulations 10000 --seed 20260905 --output runs/season
```

Use canonical IDs from [the team registry](src/epl_forecast/data/teams.csv).
`--as-of` means the start of that date. Results from that date are excluded even
if kickoff times exist. For match forecasts, `--as-of` defaults to `--date`.

Model versions, splits, training-window length and starting parameters live in
[baselines.toml](configs/baselines.toml) and [elo.toml](configs/elo.toml).
`--model` selects a model ID. The frequency and Elo models provide only H/D/A
probabilities; the Poisson models also provide score likelihoods, an explicitly
truncated display grid, and unbounded score sampling.

Evaluation writes per-match predictions, per-season metrics, calibration bins,
matched market comparisons and block-bootstrap loss differences. `run.json`
records configuration, processed-data hashes, package versions and a source-code
fingerprint. Full generated output stays in `runs/`; compact reference results
are in [docs/experiments](docs/experiments/).

The simulation command replays a historical season using its recorded fixtures.
It produces points, goal-difference and position distributions, title/relegation
chances, and top-four/top-five chances. For conditional European qualification:

```sh
uv run epl-forecast simulate --season 2024-2025 --as-of 2025-01-01 \
  --europe-scenario configs/europe_scenario.example.json --output runs/season-scenario
```

The example is a hypothetical scenario, not a prediction of cup winners. The
supported allocation assumes no extra English UEFA titleholders or eligibility
exclusions. See [simulation rules and limitations](docs/modeling.md).

## Working on the project

```sh
uv run ruff format --check
uv run ruff check
uv run pytest
```

Tests use synthetic data and need no network. The project uses ordinary modules:
`data/` acquires and normalizes sources, `models/` implements forecasting,
`evaluation.py` scores chronological predictions, and `simulation.py` resolves
season outcomes. There is no frontend or betting automation.

When testing a rebuilt wheel at the same version, use `uv run --no-cache
--no-project --with ./dist/epl_forecast-0.1.0-py3-none-any.whl ...`. Otherwise uv
can reuse an older installed wheel even after a package refresh.

To audit additional seasons, create a separate snapshot and data root:

```sh
uv run epl-forecast data fetch --start-season 2010 --end-season 2026 \
  --root data/new-audit --snapshot configs/new_snapshot.json
```

Incomplete results can be normalized and audited, but a season simulation
requires all 380 ordered fixtures. A verified live fixture adapter is future work.
Authentication is checked before retrying a restricted source; 401/403 responses
fail immediately. The initial data source needs no credentials.
