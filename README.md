# Premier League and Championship forecasts

Product objective: [north star](docs/north_star.md). Active research:
[joint forecasting architecture](docs/architecture_next_phase.md).

Probabilistic match forecasts and season simulations for England's top two leagues,
using locally archived provider data. Both leagues are supported forecasting targets.
M7 is the active structural MVP model and M2 remains its operational benchmark.
The [pinned 2026/27 projection](docs/experiments/current_season_projection_2026-09-10T18/report.md)
records the current two-league rank distributions and matched uncertainty
sensitivity, with sanctions in force and a path-conditioned Championship bracket;
[what it says and how far to trust it](docs/season_projection.md) reads it back.
The [matched research scoreboard](docs/experiments/research_scoreboard.md) keeps
their outcome, score and calibration metrics beside M5 and market comparators.
M7 is frozen as the structural season model for both leagues; the product path is
now prospective operation rather than further architecture. Realized tables carry
every sanction in force and forecasts carry only the sanctions knowable at their
cutoff, the Championship bracket runs on each simulated path's own latent states
([validation](docs/experiments/playoff_conditioning.md)), and
`scripts/verify_forecast_product.py` re-checks a published archive against the
[MVP contract](docs/mvp.md).
The [Championship season panel](docs/experiments/season_scoring_championship.md)
establishes M7 as the season product in the second league as well, and the
[relegation entry-state comparison](docs/experiments/relegation_entry.md) keeps
the current Championship treatment for clubs arriving from the Premier League.
The [chronological market pool](docs/experiments/market_pool.md) now publishes a
separate market-assisted probability when a captured pre-closing quote is available.
Existing models and the simulator supply evidence and reusable components for a
joint system; they do not prescribe its final architecture. The
[corrected player comparisons](docs/experiments/player_layer_corrections.md)
support a small [portable attacking-trait interface](docs/portable_player_interface.md).
The [MVP contract and model choice](docs/mvp.md) describe the current product.
The [short discovery sprint](docs/experiments/discovery_sprint.md) finds no new
model family ready for confirmation and keeps the draw/low-score miss as the most
useful narrow follow-up. The
[current-strength study](docs/experiments/current_strength.md) validates the
newly normalized API-Football team statistics, including the first Championship
xG in this archive, and records them as a post-MVP lead rather than a build.
Historical reports retain their original datasets and results.

## Data and forecasts

Run from the repository root with uv. Set `API_FOOTBALL_KEY` in the environment
or an ignored `.env` file. Provider access and redistribution are subject to each
provider's terms; credentials and captured data are not committed.

```sh
uv sync --locked --all-extras
uv run epl-forecast data collect
uv run epl-forecast data audit
uv run epl-forecast forecast --competition eng-premier-league
uv run epl-forecast forecast --competition eng-championship
```

Create a pinned two-league M7 season snapshot and matched uncertainty sensitivity
from one retained information cutoff with:

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/project_current_seasons.py \
  --cutoff <ISO-timestamp> --output <new-artifact-directory>
```

API-Football supplies schedules, player data, per-match team statistics and league
standings. Football-Data supplies results, odds and basic match statistics.
Understat supplies Premier League xG; no Championship xG enters any model. FPL is retained only for captured availability/news and playing
probabilities. Canonical Parquet tables under `data/parquet/` are queried through
embedded DuckDB. Immutable request records and publication manifests retain raw
hashes, provenance and actual retrieval timestamps.

```sh
uv run epl-forecast data backfill --start 2010 --max-requests 200
uv run epl-forecast data query --sql 'SELECT competition_id, season_id, count(*) FROM fixtures GROUP BY 1,2 ORDER BY 1,2'
uv run epl-forecast forecast --config configs/quality_tilt.toml --model M5-quality-tilt-v1
```

Backfills resume from successful request checkpoints and reserve daily API quota
for current collection. They complete the current season for both leagues, then
current-player transfer and sidelined histories, then the preceding three seasons,
before older history. The migration plan tracks remaining ingestion and audit work;
a successful request does not establish complete historical coverage.

`data normalize` replays every raw capture into a fresh canonical store and
publishes it only after verification, so identity corrections and provider
repairs are reproducible from immutable evidence rather than accumulated state.

Forecasts produce JSON, CSV and HTML under `runs/forecasts/`. Premier League
projections report European league positions; Championship projections report
automatic promotion, season-specific playoff qualification and promotion. Playoff
fixtures are kept separate from the regular-season table. The promotion forecast
simulates the applicable postseason bracket conditional on each regular-season
path with the structural score model. Neutral-final and tied-knockout treatments
are explicit approximations in the forecast artifact.

`--cutoff <ISO timestamp>` limits inputs to evidence retrieved by that timestamp.
Model fitting also excludes results from the forecast's London calendar date.
Retrospective backfills cannot recreate historical pre-match observations.
Unresolved live or unscheduled fixtures withhold a complete season projection.

The [migration plan](docs/data_architecture_migration.md) records collector cutover,
historical archive completeness and the conditions for retiring the plan.

## Improve the model

Use historical rolling CV for exploration and archived pre-kickoff forecasts as
the forward test. All historical seasons, including 2025/26, can inform model
development. Keep hyperparameter selection inside chronology when reporting a
selected strategy's performance. Inspect per-season scores and complementary
errors; candidates need no frozen protocol or minimum-gain threshold.

The [M5 batch report](docs/experiments/m5_quality_tilt.md) compares 4,180 matches
in 2015/16–2025/26 and checks a sampled posterior on a smaller historical subset.
M5 is near M2 on aggregate outcome loss. The [season-level comparison](docs/experiments/season_scoring.md)
now shows better early-season distribution scores and coverage for M4/M5/M7,
with tradeoffs across origins and targets; M7 supplies the structural MVP while M2
remains the benchmark. The matching
[Championship panel](docs/experiments/season_scoring_championship.md) favors M7 at
every origin through MW19. The finite dynamics grid concentrates heavily,
and synthetic league-level coverage needs improvement.

```sh
uv run epl-forecast evaluate --config configs/quality_tilt.toml \
  --split development --output runs/m5-development
uv run epl-forecast evaluate --config configs/quality_tilt.toml \
  --split validation --output runs/m5-validation
uv run epl-forecast evaluate --config configs/quality_tilt.toml \
  --split holdout --output runs/m5-holdout
uv run python scripts/diagnose_quality_tilt.py \
  --evaluations runs/m5-development runs/m5-validation runs/m5-holdout \
  --scores runs/m5-holdout --output runs/m5-diagnostics
```

The optional [NumPyro reference](docs/quality_tilt_model.md) checks approximate
inference without adding MCMC to production:

```sh
uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --output runs/m5-posterior-reference
```

Player-match rows now come from the canonical `appearances` table; inspect their
coverage with `data audit` and the recent input window with
`data/audits/recent_readiness.json`. Readiness requires eleven starters with
usable identity and minutes for each team in every finished regular fixture.
The superseded [FPL feasibility audit](docs/player_data_audit.md) is retained
as a record of the earlier dataset, not as a runnable pipeline. See the
[architecture work plan](docs/architecture_next_phase.md) for the evidence sequence
and outstanding requirements.

## Player-aware M6 research forecasts

M6 jointly fits club/system and player Quality, integrates uncertain minutes,
and propagates the same player effects through season paths. It remains a
research model; M2 is still operational. See the [M6 model](docs/player_quality_model.md)
and [batch evidence](docs/experiments/m6_player_quality.md).

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_player_quality.py \
  --season 2024-2025 --output runs/m6-evaluation
OPENBLAS_NUM_THREADS=1 uv run python scripts/diagnose_player_quality.py \
  --evaluation runs/m6-evaluation --output runs/m6-diagnostics
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/check_player_quality_posterior.py \
  --output runs/m6-reference
```

For a current player-aware export, collect current squads and use the canonical
appearance archive:

```sh
uv run epl-forecast data collect
OPENBLAS_NUM_THREADS=1 uv run python scripts/forecast_player_quality.py \
  --forecast-only --competition eng-premier-league --output runs/m6-live
```

The same command accepts `--competition eng-championship`. The optional availability
counterfactual uses an explicit 28-day recovery assumption for captured FPL round
probabilities; it is a model scenario, not a medical recovery prediction.

## Historical experiments

Backfill the canonical archive with `data backfill`; inspect gaps with `data audit`.
A checkout does not include provider data. Preserve `data/raw/`, `data/requests/`,
`data/manifests/`, `data/parquet/` and forecast runs when backing up the project.
The old CSV restoration commands have been removed. Original local snapshot and
run evidence remains on disk, but new consumers use canonical datasets.

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
scripts/verify.sh
```

That formats, lints and tests in that order, keeping the `research` extra
installed. GitHub Actions runs the same three checks on pushes to `main` and on
pull requests, with `ruff format --check` in place of the rewriting formatter;
there is no other automation. Tests use synthetic data and need no network. Keep leakage, identity, probability,
score-distribution and simulation arithmetic checks. Repeat byte-for-byte
normalization when normalization changes; reserve fresh-directory reproduction
for occasional checks and releases.

The project uses ordinary Python, NumPy and SciPy. It has a local collection
scheduler, with no hosted frontend or betting automation. Raw snapshots and generated forecasts are local,
Git-ignored artifacts; back them up if retaining the live record matters.

When testing a rebuilt wheel at the same version, use `uv run --no-cache
--no-project --with ./dist/epl_forecast-0.1.0-py3-none-any.whl ...` to avoid a stale
cached installation.

M7 research adds a pinned Understat team xG channel to the centered Quality/Tilt
parent. See [the model](docs/xg_model.md) and [batch evidence](docs/experiments/m7_xg_parent.md).
Use `configs/xg_quality_tilt.toml` for chronological comparisons; M2 remains the
operational benchmark. Historical xG availability is reconstructed, not prospective.

Season projections now have a [direct evaluation layer](docs/season_evaluation.md):
rank RPS, rank and points PIT/interval coverage, points CRPS, and event Brier scores
and reliability curves. Compare these product-level scores alongside match loss.
