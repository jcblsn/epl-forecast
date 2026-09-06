# M5 batch: Quality, Tilt and evolving seasons

September 6, 2026. M5 now supplies the architectural capabilities requested in
the steering memo. M2 remains the operational default: aggregate outcome loss is
near tied, early-season loss remains worse, and the first shared-tempo likelihood
does not improve score likelihood over its independent-Poisson ablation.

M5 reuses M4's filter and cohort promotion prior in explicit Quality/Tilt
coordinates. It adds separate stochastic processes, approximate Bayesian weights
over twelve dynamics/dispersion specifications, a shared-Gamma joint score law,
and calendar-time state evolution within season paths. Exact equivalence to M4
under matched Poisson parameters is tested. No individual promotion regression,
player model, frontend redesign or experiment-governance layer was added.

## Rolling evidence

All 4,180 PL matches in 2015/16–2025/26 use prior-date information. Model weights
use chronological joint daily predictive likelihoods, approximated by Laplace
integration. Each evaluation initializes on earlier expanding PL/Championship
history; M2 retains its existing 1,095-day PL window. These are exploratory
historical results, including the historically named holdout period.

| Model | Outcome log loss | Brier | ECE | Score NLL |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.974114 | 0.578764 | 0.013474 | 2.941520 |
| M5 shared tempo | 0.974278 | 0.578762 | 0.017507 | 2.937058 |
| M5 independent Poisson | 0.974300 | 0.578757 | 0.017703 | 2.935774 |

| Period | Matches | M2 loss | M5 loss | M5 Poisson loss |
| --- | ---: | ---: | ---: | ---: |
| 2015/16–2022/23 | 3,040 | 0.971760 | 0.971245 | 0.971225 |
| 2023/24–2024/25 | 760 | 0.957345 | 0.956878 | 0.956918 |
| 2025/26 | 380 | 1.026493 | 1.033346 | 1.033664 |
| August–September, all years | 679 | 0.965808 | 0.969803 | 0.969827 |

The [individual seasons](m5/by_season.csv), [slices](m5/slices.csv) and
[aggregate metrics](m5/overall.csv) retain the detail. Mean fixture-weighted
Quality SD is 0.0945 and Tilt SD is 0.0730; the Poisson variant has almost the
same states and uncertainty. See [state summaries](m5/states.csv).

The production grid is an initial finite approximation, not a comprehensive
hyperparameter posterior. At the September 6 live cutoff its effective number
of specifications is 1.0000003: essentially all weight goes to Quality retention
0.85 / annual SD 0.09, Tilt retention 0.5 / annual SD 0.07, and Gamma shape 100.
The surviving law is weakly overdispersed. This concentration explains much of
the small ablation difference and merits checking grid support and accumulated
evidence approximation. It is reported without artificially flattening weights.

## Draws and tails

A separate 2025/26 rolling replay exports complementary events using the full
score distribution. This narrower diagnostic does not establish a league-wide
need for any particular correction.

| Event | Observed | M2 | M5 | M5 Poisson |
| --- | ---: | ---: | ---: | ---: |
| Draw | 27.37% | 23.55% | 23.41% | 23.28% |
| 0–0 | 7.11% | 5.97% | 6.27% | 6.04% |
| Total goals ≥6 | 4.21% | 7.67% | 7.81% | 7.53% |
| Both teams score | 56.05% | 55.09% | 53.90% | 54.11% |

Shared tempo moves draws and scoreless games in the desired direction against
the ablation, but also increases an already overpredicted high-total tail.
Binary event Brier scores are in [score events](m5/score_events.csv). The evidence
supports retaining the coherent joint likelihood as a capability while continuing
to investigate its adequacy; increasing overdispersion alone is not an obvious fix.

## Posterior approximation

The optional reference fits the same component law on 90 matches in
August–October 2024, starting from population priors. Four NUTS chains each retain
800 samples after 600 warmup iterations. A fixed-parameter fit and an inferred-
parameter fit both have zero divergences, maximum reported R-hat below 1.001,
and minimum effective sample counts above 2,000 for final states and inferred
parameters. Full numerical results are in [reference evidence](m5/posterior_reference.json).

| Comparison | Mean RMS difference | Median filter/reference SD | Correlation RMS difference |
| --- | ---: | ---: | ---: |
| Fixed dynamics/dispersion | 0.00932 | 0.99883 | 0.02520 |
| Inferred dynamics/dispersion | 0.00919 | 1.00617 | 0.02479 |

For the second row, production conditional filters are integrated over 100
reference hyperparameter draws. This tests the Gaussian state approximation;
it does not validate the production grid's approximate marginal likelihoods.
The sampled dispersion posterior is broad: mean 60.4, 90% interval 13.4–170.1.
The short window also leaves substantial process-parameter uncertainty.

With known latent states drawn from the same fixed-parameter generative process,
nominal 90% final-state intervals produce:

| Method | Synthetic datasets | Quality coverage | Tilt coverage | League level | Home advantage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production filter | 200 | 90.43% | 89.80% | 83.50% | 89.00% |
| Sampled reference | 8 | 94.38% | 89.38% | 100% | 100% |

Reference coverage is especially noisy with only eight independent datasets.
All eight reference fits have zero divergences and maximum reported R-hat below
1.002. Team intervals within a dataset are correlated. These checks support
keeping the fast filter and identify league-level undercoverage for targeted
follow-up. They do not establish full-season or promotion-entry calibration.

## Live artifact and player audit

The snapshot `snapshots/2026-09-06T052122.516459Z/` captures all five live sources.
The M5 archive contains 20 Quality/Tilt summaries, 352 remaining score forecasts,
and 10,000 season paths, fixing all 28 observed results. Each path samples one
dynamics specification and joint current state, evolves league/home and Q/T
states through fixture dates, and samples independent match tempo shocks.
Simulated scores do not update those already-sampled latent strengths.

Live JSON/CSV expose Q/T means, SDs and covariance; match JSON separates rate
uncertainty from match-tempo and Poisson randomness. Future match marginals and
forward paths are checked for agreement. Unknown fixture dates suspend the M5
season projection while clearly dated hypothetical match probabilities remain
available. The original milestone archive is
`runs/forecasts/2026-09-06T052217.785124Z/`; the final verification record is
[live verification](m5/live_verification.json).

The [player feasibility note](../player_data_audit.md) and normalized table provide
253,509 player-match observations across ten seasons. All 3,800 fixture IDs and
dates match Football-Data. The audit corrects transfer-era mappings and masks
placeholder starts/xG. It recommends 2023/24 onward for complete starts/xG and
states explicitly that full historical publication/availability reconstruction
has not been established. No player model was built.

## Reproduce

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
uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --output runs/m5-posterior-reference
uv run python scripts/audit_players.py
```

Commands require fresh output directories. The original tail diagnostics used
`runs/m5-score-diagnostics/`, a second holdout replay after adding diagnostic
columns; all three proper-score results agree to displayed precision.
[Input hashes](m5/inputs.json) identify the original retained prediction files.
M2 remains the reference while M6 design and the specific M5 findings guide the
[next work](../next_experiments.md).
