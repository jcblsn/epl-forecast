# Championship season projections: M7 against M2

M7 is defensible as the Championship season product. On eleven seasons of
Championship history it beats M2 on rank RPS at preseason, MW6, MW12 and MW19,
on points CRPS at preseason, MW6 and MW12, and on every headline event Brier at
preseason, each with a season-clustered interval excluding zero. Its rank and
points PIT histograms are close to uniform at every origin, where M2's are
strongly U-shaped. No league-specific model split is needed: M7 is the product in
both competitions.

The panel contains 110 forecasts: two retained specifications, 11 seasons
2015/16–2025/26, five origins and 10,000 simulations per forecast. Scores pool 264
club-seasons per model-origin, 2,640 scored rows in total. No parameter was
selected using these scores. This is retrospective development evidence. See the
[methodology and commands](../season_evaluation.md); the Premier League panel is
in the [season scoreboard](season_scoring.md).

M4 and M5 were not run. A four-model Championship panel needed about seven hours
of refitting, which is not the "falls out of existing machinery cheaply" the batch
allowed for, and the M2/M7 contrast is the one the product decision turns on.

## The preseason entry-state defect

The first Championship panel produced a much worse M7: preseason rank RPS 0.1665
against M2's 0.1651, points CRPS 8.53 against 8.12, and a mean points SD of 19.8
points against M2's 8.6. That was a defect, not a model property.

The promotion bridge decides whether a club entering a season gives up its fitted
state. Its source is the immediately preceding Championship season, which is
correct when the forecast competition is the Premier League and wrong when it is
the Championship: every club returning to the Championship matched the bridge and
was reset to the flat league population prior. At the 2025/26 preseason cutoff,
19 of 24 Championship clubs were described by a zero-mean prior with an 0.283
quality SD, while their fitted states sat unused in the filter. Fitting itself
kept the state, so the reset applied only to forecasts made before a club's first
match of the season — which is exactly the preseason origin.

Correcting it changes the preseason column and nothing else. Every score at MW6
and later is identical between the two runs.

| Preseason metric | M2 | M7 before | M7 after |
| --- | ---: | ---: | ---: |
| Rank RPS | 0.16507 | 0.16650 | 0.15128 |
| Points CRPS | 8.124 | 8.534 | 7.554 |
| Points RMSE | 13.97 | 14.57 | 13.54 |
| Mean points SD | 8.59 | 19.80 | 12.58 |
| 50% points coverage | 34.5% | 68.9% | 53.8% |
| 90% points coverage | 73.5% | 95.8% | 88.6% |
| 90% points width | 28.2 | 65.4 | 41.4 |
| Points PIT total variation | 0.204 | 0.205 | 0.072 |

The Premier League panel is untouched: the guard applies only when the forecast
competition is not the Premier League, so the promotion path is unchanged.

The [pinned 2026/27 projection](current_season_projection_2026-09-10/report.md) is
also unaffected, because every Championship club had played by its 10 September
2026 cutoff and the reset only reached clubs with no match yet in the season.
Regenerating that artifact from the same cutoff and seed after the fix reproduces
`report.md`, `table.csv`, `rank_probabilities.csv`, `sensitivity.csv`,
`mc_noise.csv` and both heatmaps byte for byte. The three Championship forecast
JSONs differ only by two descriptive `playoff_model` fields added afterwards by
the delayed-season playoff-date handling, and the manifest differs by its recorded
commit and code hashes. No forecast number changed, so the snapshot stands.

## Scores across origins

Rank RPS, lower is better:

| Origin | M2 | M7 | M7 − M2 | Season-cluster 95% |
| --- | ---: | ---: | ---: | --- |
| preseason | 0.16507 | 0.15128 | −0.01380 | [−0.01963, −0.00735] |
| MW6 | 0.14360 | 0.13549 | −0.00811 | [−0.01114, −0.00491] |
| MW12 | 0.12451 | 0.11826 | −0.00626 | [−0.00930, −0.00269] |
| MW19 | 0.10080 | 0.09799 | −0.00280 | [−0.00533, −0.00054] |
| MW30 | 0.06345 | 0.06308 | −0.00037 | [−0.00124, +0.00052] |

Points CRPS, lower is better and measured in points:

| Origin | M2 | M7 | M7 − M2 | Season-cluster 95% |
| --- | ---: | ---: | ---: | --- |
| preseason | 8.124 | 7.554 | −0.569 | [−0.891, −0.226] |
| MW6 | 7.119 | 6.809 | −0.310 | [−0.470, −0.145] |
| MW12 | 6.145 | 5.892 | −0.253 | [−0.388, −0.109] |
| MW19 | 4.883 | 4.774 | −0.109 | [−0.224, +0.006] |
| MW30 | 3.218 | 3.195 | −0.023 | [−0.076, +0.028] |

M7 has the better preseason rank RPS in nine of the eleven seasons; 2015/16 and
2024/25 are the exceptions. The advantage closes as results accumulate, which is
what a structural prior with better entry states should do.

## Calibration

M2 is materially under-dispersed in the Championship at every origin and in both
targets, exactly as in the Premier League. Its preseason nominal 90% points
interval covers 73.5% of final totals and its nominal 50% covers 34.5%.

| Origin | Model | 50% | 80% | 90% | 95% |
| --- | --- | ---: | ---: | ---: | ---: |
| preseason | M2 points | 34.5% | 63.6% | 73.5% | 79.9% |
| preseason | M7 points | 53.8% | 79.5% | 88.6% | 92.8% |
| preseason | M2 rank | 42.8% | 71.2% | 83.3% | 89.8% |
| preseason | M7 rank | 55.7% | 84.5% | 94.3% | 97.3% |
| MW30 | M2 points | 50.0% | 77.7% | 86.0% | 92.0% |
| MW30 | M7 points | 52.3% | 81.1% | 89.4% | 96.2% |

M7's points intervals are close to nominal from preseason on. Its rank intervals
are a little too wide from the 80% level up — 94.3% coverage at nominal 90% at
preseason, and 95.1% at MW30 — so rank interval width is the one dimension where
M7 pays for its dispersion. Total variation from uniform in the PIT histograms:

| Origin | M2 points | M7 points | M2 rank | M7 rank |
| --- | ---: | ---: | ---: | ---: |
| preseason | 0.204 | 0.072 | 0.145 | 0.038 |
| MW6 | 0.196 | 0.077 | 0.164 | 0.066 |
| MW12 | 0.189 | 0.117 | 0.149 | 0.062 |
| MW19 | 0.147 | 0.098 | 0.117 | 0.049 |
| MW30 | 0.111 | 0.092 | 0.098 | 0.058 |

## Event probabilities

Brier scores, lower is better, with the season-clustered M7 − M2 interval:

| Origin | Event | M2 | M7 | M7 − M2 | 95% interval |
| --- | --- | ---: | ---: | ---: | --- |
| preseason | Title | 0.04616 | 0.03905 | −0.00712 | [−0.01100, −0.00366] |
| preseason | Automatic promotion | 0.07855 | 0.06793 | −0.01062 | [−0.01952, −0.00130] |
| preseason | Playoff qualification | 0.14052 | 0.13526 | −0.00526 | [−0.01047, −0.00033] |
| preseason | Promotion | 0.10756 | 0.09530 | −0.01226 | [−0.02438, −0.00065] |
| preseason | Relegation | 0.11189 | 0.10261 | −0.00928 | [−0.01946, +0.00101] |
| MW6 | Title | 0.03852 | 0.03551 | −0.00301 | [−0.00563, −0.00039] |
| MW30 | Promotion | 0.04498 | 0.04539 | +0.00041 | [−0.00132, +0.00212] |

Every preseason event favors M7, four of five with intervals excluding zero.
After MW12 the two models are indistinguishable on events. Promotion probabilities
include the simulated postseason bracket in every forecast; the observed truth
takes the actual playoff winner from the following season's Premier League field.

## Entry cohorts

Championship clubs divide into incumbents, clubs promoted from below and clubs
relegated from the Premier League. Preseason:

| Cohort | Clubs | Model | Rank RPS | Points CRPS | Points bias | 90% points coverage |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Incumbent | 198 | M2 | 0.15848 | 7.496 | −0.00 | 76.8% |
| Incumbent | 198 | M7 | 0.14779 | 7.159 | +0.39 | 87.9% |
| Promoted from below | 33 | M2 | 0.16426 | 7.206 | +3.54 | 81.8% |
| Promoted from below | 33 | M7 | 0.15935 | 7.309 | +3.61 | 93.9% |
| Relegated from the PL | 33 | M2 | 0.20543 | 12.808 | −2.58 | 45.5% |
| Relegated from the PL | 33 | M7 | 0.16412 | 10.171 | −3.46 | 87.9% |

Relegated clubs are the hardest cohort for both models and the largest M7 gain:
rank RPS 0.164 against 0.205 and 87.9% against 45.5% coverage. Both models
under-predict them, M7 by 3.5 points, and both over-predict clubs promoted from
below by about 3.6 points. The under-prediction of relegated clubs is what the
[relegation entry-state comparison](relegation_entry.md) tests directly; neither a
generic relegated-club prior nor a mapping from the club's Premier League season
removes it without costing coverage.

## Limits

Championship xG does not exist in this archive. M7's Understat channel therefore
contributes no evidence here, its three chance-probability members receive
identical likelihoods, and the model reduces to the centered Quality/Tilt filter
with fixed dynamics. "M7 in the Championship" means M7's dynamics and entry
handling, not its observation model.

Sanctions are Premier League only in this scorer: Championship forecasts apply no
point adjustments, while realized tables include every sanction the archive
records, so points deductions contribute to Championship forecast error in a way
they do not in the Premier League panel. EFL disciplinary tiebreaks are
unavailable, so remaining ties split rank mass equally.

Origins are match-count proxies, not fixture rounds, and the 2019/20 season's
interruption makes calendar-time and match-count origins diverge. The observed
playoff winner is inferred from the following season's Premier League membership,
which requires that season to exist in the archive.

## Reproducing

`runs/championship-season-scoring-v4`, seed 20260910, 10,000 simulations. The
[forecast manifest](season_scoring_championship/forecast_manifest.json) pins the
configs, code hashes, dependency versions and data manifest;
[evaluation_runner.txt](season_scoring_championship/evaluation_runner.txt) is the
runner as executed, before its later refactor onto the shared truth helper. The
committed [forecast marginals](season_scoring_championship/forecast_marginals.json.gz)
reproduce every score in this report without provider data:

```sh
uv run python scripts/rescore_seasons.py \
  --archive docs/experiments/season_scoring_championship/forecast_marginals.json.gz \
  --output runs/championship-rescore
```
