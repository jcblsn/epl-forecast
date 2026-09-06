# M6 player Quality: completed vertical slice

September 6, 2026. M6 can jointly represent club and player strength, react to
squad information, and propagate uncertain minutes through match and season
forecasts. The first chronological comparison does not establish a predictive
gain. M2 remains operational; M6 is archived as a research forecast.

## Model and comparison

The [model specification](../player_quality_model.md) retains persistent dynamic
club/system Quality and team Tilt, adding population-pooled scalar player
Quality. Actual training minutes enter the same daily goal likelihood as club
states, retaining their posterior cross-covariance. Player effects are static
in this first version, with Normal(0, 0.6²) priors. A full-match player's typical
share is 1/11. The population scale is fixed, not inferred or tuned to these
results. The original four independent-Poisson M5 dynamics specifications and
prior weights are preserved; shared tempo remains an available ablation.

The chronological comparison covers all 380 fixtures in 2024/25. Both models
use the same expanding PL/Championship evidence window beginning July 2023.
Thus this is a matched research-window comparison using unchanged M5 code and
support, not a reproduction of earlier all-history M5 scores. M6 uses 32 lineup
draws per specification. The oracle supplies actual target minutes to exactly
the same fitted M6 posterior; it is not forecast performance.

| Information regime | Outcome log loss | Exact-score log loss | Outcome loss difference from M5 |
| --- | ---: | ---: | ---: |
| M5 team only | 0.981930 | 2.978934 | — |
| M6 deployable | 0.984239 | 2.989247 | +0.002309 |
| M6 oracle diagnostic | 0.983004 | 2.986776 | +0.001074 |

The 95% paired match-day bootstrap intervals for the outcome differences are
[-0.001715, +0.006131] and [-0.004023, +0.005958]. These exploratory intervals
are not promotion gates. The retained [predictions](m6_quality/predictions.csv)
contain all three regimes, fixture IDs, proper scores, signed probability
changes and slice membership. [Summary](m6_quality/summary.csv) and
[diagnostics](m6_quality/diagnostics.json) retain uncertainty and the largest
movements. Deployable home-win probabilities move by an average absolute
1.31 percentage points and a maximum 4.43 points; oracle movement reaches
12.40 points.

## Where information fails to enter

| Slice | Matches | Deployable outcome loss difference | Oracle diagnostic difference |
| --- | ---: | ---: | ---: |
| Early season | 50 | +0.013675 | -0.002896 |
| Newcomer / transfer proxy | 27 | +0.015849 | +0.000014 |
| Major lineup change | 144 | +0.002546 | +0.001245 |
| Returning player | 122 | -0.000308 | -0.000582 |
| Promoted team | 108 | +0.007021 | +0.001599 |
| Goalkeeper change | 73 | -0.000548 | +0.001754 |

Slices overlap. Major changes mean at least four changes from the previous
observed starting eleven on either side. Newcomer and return slices require at
least 45 target minutes; returns follow two recorded zero-minute appearances.
These are retrospective information diagnostics, not claims that the absences
or transfers were known at forecast time. Known historical absence timestamps
are unavailable; that slice is supplied by the current snapshot scenario below.
The diagnosis script replaces the initial broad candidate-based labels without
changing predictions or refitting.

In the first 40 opening fixtures, M5 outcome loss is 0.959115, deployable M6
without carry-forward is 0.972119, and oracle M6 is 0.951980. The bounded 0.7
carry-forward membership prior changes deployable loss to 0.969507. It helps
modestly but does not repair the opening gap. It uses only players already
observed at their previous club and never discovers future arrivals. Unobserved
departures can remain in the pool, and historical publication times remain
unknown. The original [pilot](m6_quality/opening_pilot_summary.csv) is retained.

The opening and newcomer splits identify a candidate/minutes bottleneck. The
flat full-season oracle result means goals-only player identification also
remains unresolved. This is evidence against promoting this implementation,
not sufficient evidence to discard the player architecture. Retain shrinkage,
accumulate genuine forward cases, and keep any second formulation bounded.

## Sampled Bayesian reference

The [reference](m6_quality/posterior_reference.json) fits the joint trajectory on
60 real 2023/24 matches involving 424 players, with fresh population club priors
and one fixed independent-Poisson dynamics specification. Four sequential NUTS
chains use 600 warmup and 800 retained draws each. There are zero divergences,
maximum R-hat 1.00055 and minimum effective sample size 4,250 after rounding.

Player posterior mean RMS discrepancy is 0.00667; the largest mean difference
is 0.039 reference standard deviations. The median player SD ratio is 1.0013,
with a range of 0.9494–1.0527. Forecast log-rate means have RMS discrepancy
0.08269 and maximum discrepancy 0.332 reference SD. This is consistent with the
inherited common-scoring-level approximation issue. It supports retaining fast
joint inference for this slice, not claiming exact full-history inference or
validated promotion-entry uncertainty.

## Current availability and season paths

The live season snapshot was captured September 6 at 17:58 UTC, followed by
fresh player histories. It contains 30 captured full-time results, including
10 still provisional in the source, and 350 dated remaining fixtures. M6 fits
2,824 prior-date PL/Championship results and 1,028 player effects. The corrected
current forecast was archived at 18:15:08 UTC, before all 350 target kickoffs.

The archive exposes each fixture's projected club Quality, expected player
contribution, expected minutes, player uncertainty and lineup-selection
uncertainty. The latter includes uncertainty in the coefficients, not only
variation at their posterior means. Each of 2,000 season paths draws a joint
club/player posterior state, evolves club states and resamples fixture minutes.
Across 1,050 outcome probabilities, 99.714% of season-path frequencies are within
three Monte Carlo standard errors of the direct forecasts; the maximum is 3.494.
The summary correction leaves season results identical and changes direct
probabilities by at most 2.2e-16.

The captured FPL snapshot gives Manchester United's Amad availability probability
zero. The existing availability proxy assumes linear recovery over 28 days,
expiring October 4 at 17:58 UTC. This expiry is an explicit modeling assumption,
not a medically established return date. The counterfactual restores only his
availability while keeping the fitted posterior fixed.

A [response diagnostic](m6_quality/response.json), using 1,024 lineup draws per
specification and three seeds, finds:

- United's September 13 derby win probability rises by 0.253 percentage points;
  across-seed integration SD is 0.132 points.
- United's September 20 away-win probability at Fulham rises by 0.253 points;
  integration SD is 0.046 points.
- The October 10 Tottenham fixture, after expiry, has exactly zero direct effect.

The original 64-draw scenario was too noisy to resolve this small marginal
change reliably. Its [season deltas](m6_quality/availability_scenario.json) are
retained transparently: restoring Amad changes sampled mean points by -0.1175,
top-four probability by +0.003 and relegation probability by +0.007. These signs
are Monte Carlo noise at this resolution, not evidence that restoration harms
United. The higher-draw direct forecasts imply approximately +0.0156 expected
season points across the two affected fixtures. Season probabilities remain
estimated with sampling error. Scenario v1's nested lineup summaries retain
cutoff club values and selection SD at posterior mean coefficients; the revised
full forecast is authoritative for the projected decomposition and full SD.

A separately labeled hypothetical simultaneous absence of five players ranked
by learned Quality and exposure—Mbeumo, Lammens, Cunha, Shaw and Fernandes—lowers
United's derby win probability by 3.026 percentage points, with integration SD
0.066 points. This demonstrates a meaningful response to a large lineup change;
it is not an assertion that those players are currently absent. A controlled
unit test also checks the direction and expiry of a strong goalkeeper effect.

## Retained artifacts and verification

- [Current forecast](m6_quality/live_forecast.json.gz),
  [prospective archive manifest](m6_quality/live_archive.json) and
  [run inputs](m6_quality/live_run.json).
- [Matched M5 parent](m6_quality/live_parent_forecast.json.gz),
  [availability comparison](m6_quality/availability_scenario.json) and
  [restored-player season](m6_quality/restored_season.json.gz).
- [Snapshot source bundle](m6_quality/live_snapshot.tar.gz),
  [captured player observations](m6_quality/live_player_matches.csv.gz) and
  [capture report](m6_quality/live_player_capture_report.json).
- [Artifact verification](m6_quality/verification.json), including hashes,
  chronological regime coverage, prospective cutoff checks, expected-minute
  totals, match/path agreement, reference diagnostics and expiry checks.

The compressed forecast decompresses to the exact bytes hashed in the original
prospective archive. HTML and CSV exports also remain locally in
`runs/m6-quality-live-v2/current/`. The historical player/result pins predate this
batch; the committed live bundle preserves its new timestamped input evidence.

Reproduction commands are in the [README](../../README.md). Additional checks:

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/check_player_quality_response.py \
  --scenario runs/m6-quality-live-v1/scenario.json \
  --live-players runs/m6-quality-player-capture/player_matches.csv.gz \
  --output runs/m6-response-check
uv run python scripts/verify_player_quality_batch.py
uv run ruff format --check
uv run ruff check
OPENBLAS_NUM_THREADS=1 uv run pytest -q
```

All 120 tests pass, including joint covariance and incremental replay, cutoff
isolation, carry-forward transfer exclusion, nested ensemble distributions,
uncertainty summaries, expiring availability and forward score-frequency checks.
The batch establishes the requested player-aware foundation. Predictive
promotion, richer player effects and genuinely scored forward evidence remain
separate future work.
