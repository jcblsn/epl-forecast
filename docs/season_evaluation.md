# Season forecast evaluation

Match H/D/A loss does not establish the quality of season projections. Evaluate
retained candidates on final position distributions, points distributions and
headline event probabilities alongside their match scores. Better interval
coverage alone is insufficient: proper scores penalize unnecessary dispersion.

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_seasons.py \
  --output runs/season-scoring-v1 --simulations 10000
uv run python scripts/report_seasons.py \
  --evaluation runs/season-scoring-v1 --output runs/season-scoring-v1/report
```

The default comparison uses M2 attack-defense v1, M4 dynamic-hierarchical v1,
M5 quality-tilt v1 (the overdispersed model, not its Poisson control), and M7 xG v1.
Each retains its existing configuration and training window. Parameters are not
selected using these scores. This is retrospective development evidence: existing
specifications have already been explored using historical results.

## Origins and outcomes

The panel covers 2015/16–2025/26, with 20 clubs in each season. Preseason is the
start of the first match date. Historical normalized data has no round numbers;
MW6, MW12, MW19 and MW30 are explicitly match-count proxies: the next calendar
day after the 60th, 120th, 190th and 300th completed match. All results on that
date are included, so actual counts can exceed those targets. Every row records
the cutoff and number of played matches. These are not official fixture rounds,
which postponements and the COVID interruption make materially different.

Fitting and fixed results use next-day availability. Each origin is fitted from
scratch, using only eligible history; future results enter only the outcome table.
The simulation receives the retrospectively recorded future schedule, not future
scores. M7's historical xG publication dates remain reconstructed. Forecasts use
only sanctions known at the cutoff; realized final points and positions include
all final sanctions. Unexpected sanctions therefore contribute to forecast error.
Promotion means absence from the preceding Premier League season.

## Scores and calibration

For each club, rank RPS is the mean squared difference between the forecast CDF and
the observed rank step function over ranks 1 through 19. The pool of team
contributions equals tournament RPS when every season has 20 clubs. Lower is
better. The generic scorer also accepts grouped rank categories for partial
rankings; sum probability mass into those categories first. Shared observed
positions use expected score across the occupied ranks. This follows the
[Tournament Rank Probability Score definition](https://arxiv.org/abs/1912.07364).

Rank uncertainty is reported directly as forecast SD and central 50%, 80%, 90%
and 95% interval coverage and width. Rank PIT uses the same randomized discrete-CDF
construction as points PIT, with a separate seeded stream shared across models.
Both PIT histograms and both sets of intervals are reported by forecast origin.

Points CRPS is `E|X-y| - E|X-X'|/2`, computed directly from the empirical simulated
PMF. It scores both dispersion and location in points. Bias uses forecast minus
actual; RMSE, mean forecast SD and promoted-club bias are complementary diagnostics.

Points PIT is randomized for discrete totals: `F(y-) + U p(y)`. A separate seeded
randomizer is shared across models for each club and origin. Histograms contain
10 equal-width bins, including PIT 1 in the last bin. Central 50%, 80%, 90% and
95% intervals use inverse-CDF integer quantiles and inclusive coverage; widths
are also reported. Discreteness can produce coverage above the nominal level.

Title, top-four and relegation have Brier scores and reliability curves using 10
fixed-width probability bins. Empty bins remain in CSV with missing means. Plot
marker area reflects counts; sparse high-probability bins should not be read as
precise calibration estimates. These events refer to table positions.

Each model-origin summary pools 220 club-seasons; origins are reported separately,
not treated as independent replications. Per-season summaries accompany the pool.
Paired differences versus M2 use identical clubs and origins. Their percentile
95% bootstrap intervals resample 11 whole seasons, preserving within-table
outcome dependence. Pooling 220 contributions does not create 220 independent
league winners, and these intervals remain imprecise with 11 clusters.

## Artifacts and resuming

The evaluator writes a manifest containing configurations, normalized-data
provenance, code hashes, seed and simulation count; 220 full forecast JSON files;
club-season rows; pooled summaries; per-season summaries; and calibration bins.
The reporter exports paired comparisons and standalone PNG calibration figures.
Each forecast is checkpointed and an unchanged command resumes completed cells.
Changes to recorded inputs or code reject reuse; choose a new output directory.
Raw forecasts remain under Git-ignored `runs/`; retain the directory for auditing.

The committed [11-season comparison](experiments/season_scoring.md) includes
compressed forecast marginals and realized tables. To rescore those without the
historical data cache or model fitting:

```sh
uv run python scripts/rescore_seasons.py \
  --archive docs/experiments/season_scoring/forecast_marginals.json.gz \
  --output runs/season-rescored
uv run python scripts/report_seasons.py \
  --evaluation runs/season-rescored --output runs/season-rescored/report
```

The rescore manifest hashes the archive, scorer and runner. PIT uses a separate
`SeedSequence([forecast_seed, 0x504954])` stream, shared across models for paired
club-origin comparisons. The report also exports promoted and incumbent subgroups.
