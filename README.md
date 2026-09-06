# Open Premier League forecast

An open, real-time probabilistic Premier League forecasting and season-simulation
model using free data. The aim is the strongest practical model we can build,
with current, interpretable forecasts. Reproducible experiments help improve and
validate the model; the forecasts are the product.

The project now archives live FPL and Football-Data responses and produces a
2026/27 forecast as JSON, CSV and a static HTML page. Refreshes are manual for now.
M2 remains the default reference. The M4 prototype adds dynamic attack/defense,
Championship-informed promotion priors and approximate posterior uncertainty in
match and season forecasts. Historical results cover 16 PL and Championship
seasons. The [north star](docs/north_star.md) describes the intended architecture.

## Capture and forecast

Run from the repository root with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run epl-forecast data snapshot --season-start 2026
```

This creates `snapshots/<UTC timestamp>/` containing FPL players/availability,
fixtures/results, Football-Data latest fixtures/odds, and current PL and
Championship result files. Raw bytes, retrieval times and hashes are retained.
Successful responses survive a partial source failure. No API key is needed.

Pass the printed snapshot directory to the forecast command:

```sh
uv run epl-forecast forecast --snapshot snapshots/<UTC timestamp>
```

To use M4 and propagate its posterior uncertainty into the season forecast:

```sh
uv run epl-forecast forecast --config configs/dynamic.toml \
  --model M4-dynamic-hierarchical-v1 --snapshot snapshots/<UTC timestamp>
```

Open the printed `runs/forecasts/<UTC timestamp>/index.html`. Each run archives:

- current attack/defense strengths and each team's next-match probabilities;
- all remaining H/D/A probabilities and exact-score matrices with tail mass;
- expected final points, position distributions, title, top-four/five and relegation chances;
- the captured schedule, source provenance and actual forecast archival time.

Completed scores, including today's provisional full-time FPL results, stay fixed
in the season projection. Model fitting retains the conservative rule of using
results before the snapshot's London calendar date. A game in progress suspends
the season projection while upcoming-match forecasts remain available.

Top-four/five chances describe positions. To add conditional European qualification,
pass `--europe-scenario configs/europe_scenario.example.json`, which supplies
hypothetical cup winners and league UCL places. M2 uses fixed fitted strengths.
M4 samples one joint current state per season path and holds it throughout that
path. Future state evolution, injuries and transfers are not yet modeled.
See [live operation and limitations](docs/live.md).

## Improve the model

Use historical rolling CV for exploration and archived pre-kickoff forecasts as
the forward test. All historical seasons, including 2025/26, can inform model
development. Keep hyperparameter selection inside chronology when reporting a
selected strategy's performance. Inspect per-season scores and complementary
errors; candidates need no frozen protocol or minimum-gain threshold.

The first [M4 comparison](docs/experiments/m4_dynamic.md) covers 4,180 matches in
2015/16–2025/26. Aggregate outcome loss is nearly tied with M2; early-season
performance and posterior calibration still need work. The new architecture is
functional, but these results do not justify replacing the default model.

Run rolling evaluation, then inspect promotion, uncertainty and form diagnostics:

```sh
uv run epl-forecast evaluate --config configs/dynamic.toml \
  --split development --output runs/m4-development
uv run epl-forecast evaluate --config configs/dynamic.toml \
  --split validation --output runs/m4-validation
uv run epl-forecast evaluate --config configs/dynamic.toml \
  --split holdout --output runs/m4-holdout
uv run python scripts/diagnose_dynamic.py \
  --evaluations runs/m4-development runs/m4-validation runs/m4-holdout \
  --output runs/m4-diagnostics
```

See the [M4 formulation and limitations](docs/dynamic_model.md) and the
[research queue](docs/next_experiments.md). The completed
[M2 search](docs/experiments/m2_tuning.md) found its defaults in the best region;
`scripts/tune_m2.py` remains available without being the next workstream.

## Historical experiments

The existing normalized cache is required for forecasts. On a new checkout:

```sh
uv run epl-forecast data restore
uv run epl-forecast data normalize
```

Historical raw files are pinned in [data_snapshot.json](configs/data_snapshot.json).
If an upstream file changes, restoration fails explicitly; preserve the original
raw cache for long-term reproduction. Live captures use separate timestamped
snapshots and never replace the historical pin.

The original [E001](docs/experiments/E001.md) and [E002](docs/experiments/E002.md)
reports remain records of the work already done. Their gates and split names are
historical conventions, not requirements for new exploration. For occasional
full reproduction:

```sh
uv run python scripts/reproduce.py --output runs/reproduction
uv run python scripts/reproduce.py --config configs/elo.toml --output runs/elo-reproduction
```

Other historical commands remain available:

```sh
uv run epl-forecast evaluate --split development --output runs/development
uv run epl-forecast simulate --season 2024-2025 --as-of 2025-01-01 \
  --simulations 10000 --output runs/season
uv run epl-forecast predict --season 2024-2025 --date 2024-08-17 \
  --home arsenal --away wolverhampton-wanderers --output runs/match.json
```

Historical `--as-of` means the start of the date, excluding that day's results.
Use canonical IDs from [the team registry](src/epl_forecast/data/teams.csv).

## Development

```sh
uv run ruff format --check
uv run ruff check
uv run pytest
```

Tests use synthetic data and need no network. Keep leakage, identity, probability,
score-distribution and simulation arithmetic checks. Repeat byte-for-byte
normalization when normalization changes; reserve fresh-directory reproduction
for occasional checks and releases.

The project uses ordinary Python, NumPy and SciPy. It has no hosted frontend,
scheduler or betting automation. Raw snapshots and generated forecasts are local,
Git-ignored artifacts; back them up if retaining the live record matters.

When testing a rebuilt wheel at the same version, use `uv run --no-cache
--no-project --with ./dist/epl_forecast-0.1.0-py3-none-any.whl ...` to avoid a stale
cached installation.
