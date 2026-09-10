# Championship season projections: M7 against M2

M7 is defensible as the Championship season product. On eleven seasons of
Championship history it beats M2 on rank RPS at preseason, MW6, MW12 and MW19,
on points CRPS at preseason, MW6 and MW12, and on four of five headline event
Briers at preseason, each with a season-clustered interval excluding zero. Its
rank and points PIT histograms are close to uniform at every origin, where M2's
are strongly U-shaped. No league-specific model split is needed: M7 is the product
in both competitions.

This is the corrected panel. It scores against the sanctioned final tables rather
than results-only tables, applies to each forecast only the sanctions knowable at
its cutoff, and runs the playoff bracket on each simulated path's own latent
states. Every score moved; no model-selection conclusion did.

The panel contains 110 forecasts: two retained specifications, 11 seasons
2015/16–2025/26, five origins and 10,000 simulations per forecast. Scores pool 264
club-seasons per model-origin, 2,640 scored rows in total. No parameter was
selected using these scores. This is retrospective development evidence. See the
[methodology and commands](../season_evaluation.md); the Premier League panel is
in the [season scoreboard](season_scoring.md).

M4 and M5 were not run. A four-model Championship panel was started and abandoned:
it completed 10 of 220 forecasts in twenty minutes, extrapolating to roughly seven
hours of refitting, which is not the "falls out of existing machinery cheaply" the
batch allowed for. The M2/M7 contrast is the one the product decision turns on.

## The preseason entry-state defect

The first Championship panel produced a much worse M7: preseason rank RPS 0.1665
against M2's 0.1651, points CRPS 8.53 against 8.12, and a mean points SD of 19.8
points against M2's 8.6. That was a defect, not a model property. The numbers in
this section are the ones that diagnosed it, scored against the results-only truth
this panel has since replaced; they are kept as they were measured.

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

The [pinned 2026/27 projection](current_season_projection_2026-09-10/report.md) was
also unaffected by that fix, because every Championship club had played by its
10 September 2026 cutoff and the reset only reached clubs with no match yet in the
season. It does predate the playoff-conditioning correction and Southampton's
four-point sanction, both of which reached the archive later the same day; the
[season projection guide](../season_projection.md) says what that means for it.
Regenerating that artifact from the same cutoff and seed after the fix reproduces
`report.md`, `table.csv`, `rank_probabilities.csv`, `sensitivity.csv`,
`mc_noise.csv` and both heatmaps byte for byte. The three Championship forecast
JSONs differ only by two descriptive `playoff_model` fields added afterwards by
the delayed-season playoff-date handling, and the manifest differs by its recorded
commit and code hashes. No forecast number changed, so the snapshot stands.

## What the corrections changed

Truth was previously the table a season's results imply, which is not the table any
of these seasons finished on: seven of the eleven carry Championship sanctions
totalling 94 points, and none of them reached the realized table. Forecasts, in
turn, applied no Championship sanction at any origin, including sanctions that had
been announced months before the cutoff.

Both are now fixed, and the size of the fix is checkable arithmetic. Mean points
error moves by exactly the same amount for both models — +0.31061 at preseason and
MW6, +0.28788 at MW12, +0.23106 at MW19 and MW30 — because it is a property of
truth, not of a model. At preseason that is 82 points over 264 club-seasons: the 94
sanctioned points now in the realized tables, less the 12 that Sheffield Wednesday's
July 2020 deduction already put into the 2020/21 forecasts before its November
appeal cut it to six. By MW19 the gap has fallen to 61 points, because Derby's two
2021/22 deductions and Reading's are by then knowable and the forecasts carry them.

Rank RPS improves for both models at every origin, by 0.0001 to 0.0021, since the
realized ranks the models are scored against are now the actual ones. Points CRPS
worsens for both by 0.12 to 0.18 points, which is the cost of being scored against
deductions a forecast could not have known. Neither is a model effect.

The [comparison artifact](season_scoring_championship/metric_changes.csv) records
every metric at every origin for both models. Of the 35 origin-by-metric proper
scores that name a leading model, 34 name the same one as before. The exception is
promotion Brier at MW6, where M7 led by 0.00028 and M2 now leads by 0.00024, on a
Brier near 0.082. That is a 0.3% gap on one metric at one origin, and the product
decision does not turn on it.

The playoff correction contributes nothing to the regular-season columns by
construction and is validated separately in the
[conditioning check](playoff_conditioning.md).

One season has no sanctioned table. The retained API-Football standings snapshot
for 2017/18 Championship is a partial mid-season table, not a final one: it
describes 31 or 32 played matches per club, which is internally consistent with the
archive over that prefix and therefore yields no sanction and no completed table.
That season falls back to results alone, and `sanctions.json` names it.

## Scores across origins

Rank RPS, lower is better:

| Origin | M2 | M7 | M7 − M2 | Season-cluster 95% |
| --- | ---: | ---: | ---: | --- |
| preseason | 0.16299 | 0.15008 | −0.01291 | [−0.01897, −0.00640] |
| MW6 | 0.14166 | 0.13390 | −0.00776 | [−0.01055, −0.00464] |
| MW12 | 0.12378 | 0.11766 | −0.00611 | [−0.00936, −0.00243] |
| MW19 | 0.09931 | 0.09661 | −0.00270 | [−0.00524, −0.00036] |
| MW30 | 0.06334 | 0.06293 | −0.00041 | [−0.00123, +0.00044] |

Points CRPS, lower is better and measured in points:

| Origin | M2 | M7 | M7 − M2 | Season-cluster 95% |
| --- | ---: | ---: | ---: | --- |
| preseason | 8.291 | 7.731 | −0.560 | [−0.894, −0.206] |
| MW6 | 7.250 | 6.951 | −0.299 | [−0.457, −0.134] |
| MW12 | 6.308 | 6.064 | −0.244 | [−0.389, −0.090] |
| MW19 | 5.000 | 4.896 | −0.104 | [−0.220, +0.010] |
| MW30 | 3.345 | 3.325 | −0.021 | [−0.073, +0.029] |

M7 has the better preseason rank RPS in nine of the eleven seasons; 2015/16 and
2024/25 are the exceptions. The advantage closes as results accumulate, which is
what a structural prior with better entry states should do.

## Calibration

M2 is materially under-dispersed in the Championship at every origin and in both
targets, exactly as in the Premier League. Its preseason nominal 90% points
interval covers 73.5% of final totals and its nominal 50% covers 34.5%.

| Origin | Model | 50% | 80% | 90% | 95% |
| --- | --- | ---: | ---: | ---: | ---: |
| preseason | M2 points | 34.1% | 63.6% | 73.1% | 78.8% |
| preseason | M7 points | 53.8% | 79.2% | 87.5% | 91.7% |
| preseason | M2 rank | 44.3% | 72.7% | 84.5% | 89.8% |
| preseason | M7 rank | 55.3% | 84.8% | 95.1% | 97.0% |
| MW30 | M2 points | 50.0% | 77.3% | 84.8% | 90.9% |
| MW30 | M7 points | 52.3% | 80.3% | 88.3% | 94.7% |

M7's points intervals are close to nominal from preseason on. Its rank intervals
are a little too wide from the 80% level up — 94.3% coverage at nominal 90% at
preseason, and 95.1% at MW30 — so rank interval width is the one dimension where
M7 pays for its dispersion. Total variation from uniform in the PIT histograms:

| Origin | M2 points | M7 points | M2 rank | M7 rank |
| --- | ---: | ---: | ---: | ---: |
| preseason | 0.204 | 0.076 | 0.136 | 0.045 |
| MW6 | 0.190 | 0.086 | 0.147 | 0.057 |
| MW12 | 0.192 | 0.129 | 0.149 | 0.057 |
| MW19 | 0.151 | 0.102 | 0.117 | 0.051 |
| MW30 | 0.111 | 0.083 | 0.083 | 0.047 |

## Event probabilities

Brier scores, lower is better, with the season-clustered M7 − M2 interval:

| Origin | Event | M2 | M7 | M7 − M2 | 95% interval |
| --- | --- | ---: | ---: | ---: | --- |
| preseason | Title | 0.04616 | 0.03905 | −0.00712 | [−0.01100, −0.00366] |
| preseason | Automatic promotion | 0.07856 | 0.06793 | −0.01062 | [−0.01952, −0.00130] |
| preseason | Playoff qualification | 0.14053 | 0.13524 | −0.00529 | [−0.01057, −0.00033] |
| preseason | Promotion | 0.10762 | 0.09548 | −0.01214 | [−0.02448, −0.00021] |
| preseason | Relegation | 0.10654 | 0.09883 | −0.00771 | [−0.01730, +0.00183] |
| MW6 | Title | 0.03852 | 0.03551 | −0.00301 | [−0.00563, −0.00039] |
| MW6 | Promotion | 0.08201 | 0.08225 | +0.00024 | [−0.00675, +0.00783] |
| MW30 | Promotion | 0.04493 | 0.04576 | +0.00083 | [−0.00127, +0.00297] |

Every preseason event favors M7, four of five with intervals excluding zero.
After MW12 the two models are indistinguishable on events. Promotion probabilities
include the simulated postseason bracket in every forecast; the observed truth
takes the actual playoff winner from the following season's Premier League field.

## Entry cohorts

Championship clubs divide into incumbents, clubs promoted from below and clubs
relegated from the Premier League. Preseason:

| Cohort | Clubs | Model | Rank RPS | Points CRPS | Points bias | 90% points coverage |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Incumbent | 198 | M2 | 0.15626 | 7.668 | +0.34 | 76.3% |
| Incumbent | 198 | M7 | 0.14653 | 7.346 | +0.73 | 86.9% |
| Promoted from below | 33 | M2 | 0.16015 | 7.388 | +3.72 | 81.8% |
| Promoted from below | 33 | M7 | 0.15577 | 7.476 | +3.80 | 90.9% |
| Relegated from the PL | 33 | M2 | 0.20620 | 12.936 | −2.34 | 45.5% |
| Relegated from the PL | 33 | M7 | 0.16567 | 10.302 | −3.22 | 87.9% |

Relegated clubs are the hardest cohort for both models and the largest M7 gain:
rank RPS 0.166 against 0.206 and 87.9% against 45.5% coverage. Both models
under-predict them, M7 by 3.2 points, and both over-predict clubs promoted from
below by about 3.8 points. The under-prediction of relegated clubs is what the
[relegation entry-state comparison](relegation_entry.md) tests directly; neither a
generic relegated-club prior nor a mapping from the club's Premier League season
removes it without costing coverage.

## Limits

Championship xG does not exist in this archive. M7's Understat channel therefore
contributes no evidence here, its three chance-probability members receive
identical likelihoods, and the model reduces to the centered Quality/Tilt filter
with fixed dynamics. "M7 in the Championship" means M7's dynamics and entry
handling, not its observation model.

Sanction dates are reviewed claims, not retained provider documents. The
magnitudes are checked against the provider's final table and must agree with it,
but the announcement dates come from a reviewed registry, and six Championship
sanctions in the panel window have no established date: Wigan 2019/20, Reading and
Wigan 2022/23, Sheffield United 2024/25, and all three 2025/26 deductions. Those
enter the realized table and no forecast, which understates what a forecaster could
have known at the later origins of those seasons. Five of the six were late-season
or post-season decisions, where the understatement reaches at most the MW30 origin;
the 2025/26 sanctions are the ones where this matters most and least is known.

EFL disciplinary tiebreaks are unavailable, so remaining ties split rank mass
equally.

Origins are match-count proxies, not fixture rounds, and the 2019/20 season's
interruption makes calendar-time and match-count origins diverge. The observed
playoff winner is inferred from the following season's Premier League membership,
which requires that season to exist in the archive.

## Reproducing

`runs/championship-season-scoring-v7`, seed 20260910, 10,000 simulations. The
[forecast manifest](season_scoring_championship/forecast_manifest.json) pins the
configs, code hashes, dependency versions, data manifest, both reviewed sanction
registries and the per-season sanction audit;
[evaluation_runner.txt](season_scoring_championship/evaluation_runner.txt) is the
runner as executed. [sanctions.json](season_scoring_championship/sanctions.json)
records what was derived for each season and which season has no sanctioned table.
The committed [forecast marginals](season_scoring_championship/forecast_marginals.json.gz)
reproduce every score in this report without provider data, exactly:

```sh
uv run python scripts/rescore_seasons.py \
  --archive docs/experiments/season_scoring_championship/forecast_marginals.json.gz \
  --output runs/championship-rescore
```
