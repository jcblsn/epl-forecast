# Entry priors for a club crossing a division boundary

## Decision

Replace the implicit entry rule with one generic rule. A club that played the
forecast competition last season carries the state the filter already holds for
it. Every other club — promoted, relegated, or arriving from a division the
model does not track — is initialized from a prior learned for its transition,
conditioned on the freshest evidence that actually exists for it: its
immediately preceding source-division season where that division is modeled,
and its own older target-division season weighted by a learned decay.

`entry_prior` now defaults to `memory`, the full rule. Setting it to `None`
restores the previous split behavior, where a promoted club used the
Championship bridge and every other entrant kept whatever target-division state
it last held, however old. M2, the operational match benchmark, is a different
model class and is unchanged.

The rule is never resolvedly worse than the rule it replaces on any proper
score, at any origin, in either division. It is resolvedly better for clubs
entering the Championship from outside the modeled panel, which is exactly the
cohort the previous rule had nothing to say about. It replaces a two-case
special rule with one case.

## The question

The previous rule was never stated as a rule. Promotion into the Premier League
ran through a fitted bridge; entry into the Championship ran through whatever
Championship state survived in the filter. West Ham enter the Championship in
2026/27 with a Championship state last updated in 2011/12. Fifteen years of
mean reversion leave that state at +0.03 attack with SD 0.19 — almost exactly
the stationary distribution — so the old rule describes a relegated Premier
League club as an average Championship club, and describes a club promoted from
League One the same way. The realized difference between those two cohorts is
about 0.21 in attack and 0.24 in defence.

## Matched experiment

`runs/entry-prior-v2`, ten Premier League and ten Championship seasons
2016/17–2025/26, 90 boundary crossers, 811 opening appearances and 4,000 season
paths per cell. All five treatments share the M7 fixed-p=0.2 parent for their
division, incumbent state, dynamics, conditional Poisson score law, sanction
registry and fixture schedule; only the entrants' priors differ. Each club
contributes its first ten appearances, and a match between two entrants is
counted once. Seasons are scored at preseason and at MW6.

| Treatment | Prior for a club entering the division |
| --- | --- |
| `current` | The previous rule: Championship bridge into the Premier League, otherwise the club's last target-division state decayed by elapsed time, or the flat population prior when it has none |
| `population` | The flat target-league population prior for every entrant |
| `transition` | Intercept only, learned from earlier entrants making the same transition |
| `source` | Transition prior plus the club's immediately preceding source-division season, where that division is modeled |
| `memory` | Source prior plus the club's own older target-division season, weighted by a learned decay timescale |

Three transitions appear in the panel: Championship into the Premier League,
Premier League into the Championship, and outside into the Championship. The
third covers clubs arriving from League One, whose source division is not in the
archive; they receive a transition prior with no source term, which is the
honest description of what is known about them. No provider, competition or
backfill was added for this pass.

## Labels and chronology

Coefficients are fitted on the club's whole-season division-relative target
strength — a smoothed retrospective state, used only to discover the mapping.
The first-ten-match label the earlier bridges trained on is retained as an
evaluation diagnostic and as a switch, but it is too noisy to train on: its own
measurement SD averages about 0.26 against a cohort spread near 0.22, so the
errors-in-variables fit attributes nearly all of the observed spread to
measurement noise and returns a residual SD around 0.08. Training on the season
label roughly doubles the learned residual SD — 0.076 to 0.128 for Championship
into the Premier League in attack, 0.078 to 0.164 for the reverse — while
leaving the intercepts unchanged. That is the dispersion correction; the earlier
relegation bridge's overconfidence was a label problem, not a mean problem.

Every entry prior uses only transitions whose target season finished and was
available before the forecast cutoff. Training cohorts grow from 12 to 42 per
transition. No evaluated season's own label enters its own prior.

## The learned translation

Fitted on all 42 earlier cohorts per transition, for the 2025/26 entries.
Coordinates are log-rate attack and defensive strength relative to the division.

| Transition | Dimension | Intercept | Source slope | Memory slope | Residual SD |
| --- | --- | ---: | ---: | ---: | ---: |
| Championship → PL | attack | −0.276 (0.060) | +0.247 (0.199) | +0.221 (0.150) | 0.119 |
| Championship → PL | defence | −0.184 (0.058) | +0.033 (0.169) | +0.358 (0.214) | 0.125 |
| PL → Championship | attack | +0.127 (0.058) | +0.115 (0.142) | +0.413 (0.183) | 0.148 |
| PL → Championship | defence | +0.180 (0.086) | +0.435 (0.229) | +0.244 (0.177) | 0.161 |
| outside → Championship | attack | −0.070 (0.042) | — | −0.017 (0.199) | 0.165 |
| outside → Championship | defence | −0.100 (0.029) | — | +0.029 (0.142) | 0.081 |

The intercepts are the division-level part of the signal and are the best
determined coefficients in the table: a promoted club enters the Premier League
roughly 0.28 log rate below average in attack, a relegated club enters the
Championship roughly 0.13 above it, and a club arriving from League One enters
0.07 to 0.10 below it. Residual attack/defence correlation is estimated at
+0.14 to +0.22 after shrinkage, so the prior is no longer diagonal.

In three of the four dimensions with a modeled source, the club's own older
target-division season carries a larger coefficient than its immediately
preceding source-division season. Both are 1.2 to 2.3 standard errors from
zero, so this ordering is suggestive rather than resolved, but it is the reason
`memory` outperforms `source`. Where there is no transferable memory — a League
One club's old Championship season — the fitted slope is −0.017 and +0.029, and
the rule correctly learns to ignore it.

## The memory decay

The weight on an old target-division season is `exp(-(age - 2) / tau)`, with
`tau` marginalized over a grid that includes no decay at all. The posterior is
diffuse but never concentrates on the no-decay hypothesis: at the 2025/26 cutoff
it puts 0.16 on no decay in the Premier League model and 0.28 in the
Championship model, with the rest spread over timescales from three months to
eight years. The implied expected weight on a club's last target-division season
is:

| Age of the old state | Premier League model | Championship model |
| --- | ---: | ---: |
| 2 years | 1.00 | 1.00 |
| 3 years | 0.73 | 0.59 |
| 5 years | 0.51 | 0.44 |
| 10 years | 0.30 | 0.34 |

Old evidence is discounted to about half its weight within three to five years
and a third by ten. No arbitrarily old state carries full weight because it
exists, and none is discarded outright.

## Forecast performance

Boundary crossers, 90 club-seasons per cell. Lower loss is better.

| Prior | Origin | Rank RPS | Points CRPS | 90% coverage | 90% width |
| --- | --- | ---: | ---: | ---: | ---: |
| `current` | preseason | 0.1468 | 8.542 | 84.4% | 44.64 |
| `population` | preseason | 0.1832 | 10.449 | 97.8% | 68.50 |
| `transition` | preseason | 0.1430 | 8.508 | 80.0% | 39.04 |
| `source` | preseason | 0.1396 | 8.396 | 80.0% | 38.56 |
| `memory` | preseason | 0.1374 | 8.225 | 81.1% | 39.03 |
| `current` | MW6 | 0.1142 | 6.649 | 88.9% | 35.73 |
| `population` | MW6 | 0.1237 | 7.020 | 92.2% | 42.12 |
| `transition` | MW6 | 0.1133 | 6.723 | 90.0% | 33.57 |
| `source` | MW6 | 0.1130 | 6.731 | 90.0% | 33.04 |
| `memory` | MW6 | 0.1123 | 6.647 | 87.8% | 33.29 |

Opening appearances, pooled across both divisions.

| Prior | First five (414) log loss | Score NLL | First ten (811) log loss | Score NLL |
| --- | ---: | ---: | ---: | ---: |
| `current` | 1.02469 | 2.90037 | 1.01729 | 2.89046 |
| `population` | 1.05083 | 2.94349 | 1.04820 | 2.94030 |
| `transition` | 1.02664 | 2.89772 | 1.02178 | 2.89091 |
| `source` | 1.02516 | 2.89474 | 1.02125 | 2.88982 |
| `memory` | 1.02404 | 2.89811 | 1.01930 | 2.89105 |

Season-clustered 95% intervals on paired differences; positive is worse than
the comparator. Full rows in [comparisons.json](entry_prior/comparisons.json).

| Scope | Comparison | Metric | Difference | 95% interval |
| --- | --- | --- | ---: | --- |
| Preseason crossers | `population` − `current` | points CRPS | +1.908 | [+0.933, +2.927] |
| Preseason crossers | `population` − `current` | rank RPS | +0.0363 | [+0.0149, +0.0588] |
| Preseason crossers | `memory` − `current` | rank RPS | −0.0094 | [−0.0213, +0.0012] |
| Preseason crossers | `memory` − `current` | points CRPS | −0.317 | [−0.949, +0.278] |
| Preseason crossers | `memory` − `current` | 90% coverage | −0.033 | [−0.083, +0.011] |
| Preseason crossers | `memory` − `current` | 90% width | −5.61 | [−7.41, −3.60] |
| Preseason, all clubs | `memory` − `current` | rank RPS | −0.0021 | [−0.0047, +0.0001] |
| Preseason, all clubs | `memory` − `current` | points CRPS | −0.069 | [−0.209, +0.060] |
| MW6 crossers | `memory` − `current` | points CRPS | −0.002 | [−0.461, +0.426] |
| First five appearances | `memory` − `current` | H/D/A log loss | −0.0006 | [−0.0057, +0.0047] |
| First ten appearances | `memory` − `current` | H/D/A log loss | +0.0020 | [−0.0027, +0.0064] |
| First ten appearances | `memory` − `current` | score NLL | +0.0006 | [−0.0050, +0.0073] |

The flat population prior loses on every proper score at every scope, so the
answer to whether a population prior would do just as well is no. `memory`
improves every preseason season score against the previous rule without a
resolved coverage loss, and narrows the crossers' 90% points interval by 5.6
points. Match-level differences are inside noise in both directions. By MW6 six
results have dissolved almost all of the difference, as they should.

## Where the information is

Preseason points CRPS by transition, 30 club-seasons per cell.

| Transition | `current` | `transition` | `source` | `memory` |
| --- | ---: | ---: | ---: | ---: |
| Championship → PL | 7.816 | 8.168 | 8.096 | 8.026 |
| PL → Championship | 10.306 | 10.482 | 10.223 | 10.017 |
| outside → Championship | 7.503 | 6.874 | 6.868 | 6.631 |

| Scope | Comparison | Metric | Difference | 95% interval |
| --- | --- | --- | ---: | --- |
| Championship → PL | `transition` − `current` | points CRPS | +0.351 | [+0.027, +0.659] |
| Championship → PL | `memory` − `current` | points CRPS | +0.210 | [−0.234, +0.738] |
| PL → Championship | `memory` − `current` | points CRPS | −0.289 | [−1.828, +1.235] |
| outside → Championship | `memory` − `current` | rank RPS | −0.0186 | [−0.0295, −0.0079] |
| outside → Championship | `memory` − `current` | points CRPS | −0.872 | [−1.346, −0.411] |

An intercept alone is resolvedly worse than the existing promotion bridge in the
Premier League direction, which is what a bespoke fitted bridge should be able
to claim. Adding source and memory closes that gap to within noise. All of the
resolved gain comes from the cohort the previous rule handled worst: clubs
entering the Championship from outside the panel, where `memory` takes 0.87
points off the CRPS and improves 90% coverage from 90.0% to 93.3% while cutting
the interval from 50.5 to 41.1 points.

## No recent history against recent returners

Preseason points CRPS by the age of any previous target-division state.

| Age of previous state | Clubs | `current` | `transition` | `source` | `memory` |
| --- | ---: | ---: | ---: | ---: | ---: |
| None | 20 | 8.213 | 7.895 | 7.488 | 7.826 |
| Two or three years | 48 | 7.914 | 8.264 | 8.220 | 7.697 |
| Four years or more | 22 | 10.211 | 9.599 | 9.605 | 9.739 |

| Scope | Comparison | Metric | Difference | 95% interval |
| --- | --- | --- | ---: | --- |
| No target history | `source` − `transition` | rank RPS | −0.0075 | [−0.0138, −0.0017] |
| No target history | `source` − `transition` | points CRPS | −0.407 | [−0.822, −0.055] |
| No target history | `memory` − `source` | points CRPS | +0.337 | [−0.001, +0.804] |
| Recent returner | `memory` − `source` | points CRPS | −0.523 | [−1.075, −0.057] |
| Stale history | `memory` − `source` | points CRPS | +0.135 | [−0.008, +0.287] |
| Stale history | `transition` − `current` | rank RPS | −0.0143 | [−0.0285, +0.0002] |

This is the diagnostic the hierarchy was built for, and each level earns its
place in a different cell. Source evidence is resolvedly worth having exactly
when there is no target-division history to fall back on. A two- or
three-year-old target state is resolvedly worth having, and it is the one cell
where `transition` and `source` are worse than the rule they replace, because
they discard information the previous rule kept. A state four years old or older
is worth nothing: `memory` is no better than `source` there, consistent with a
decay that has already halved its weight, and both beat unconditional
resurrection.

## Predictive dispersion

Prior against the realized whole-season target strength, 90 clubs per cell.

| Prior | Dimension | Prior SD | RMSE | Bias | Gaussian log score |
| --- | --- | ---: | ---: | ---: | ---: |
| `current` | attack | 0.183 | 0.208 | +0.013 | −0.114 |
| `current` | defence | 0.190 | 0.214 | −0.013 | −0.129 |
| `population` | attack | 0.400 | 0.285 | +0.080 | +0.282 |
| `transition` | attack | 0.150 | 0.210 | +0.033 | −0.106 |
| `source` | attack | 0.153 | 0.213 | +0.035 | −0.096 |
| `memory` | attack | 0.158 | 0.211 | +0.036 | −0.100 |
| `memory` | defence | 0.134 | 0.218 | −0.012 | −0.152 |

Entry log score against the realized entry label is +0.0041 better for `memory`
than for `current`, with a season-clustered interval of [−0.072, +0.070]: the
two are indistinguishable on entry accuracy, and the season-forecast gain comes
from the transition means rather than from sharper club ordering. The learned
priors are tighter than the decayed state they replace — 0.134 against 0.190 in
defence — and the forecasts they produce do not lose resolved coverage, so the
tightening is earned in a way the earlier relegation bridge's was not. The one
corner that still looks overconfident is defence for clubs entering the
Championship from outside, whose residual SD fits at 0.081; coverage in that
cell improves rather than degrades, so this is a flag for the next pass, not a
defect this experiment can resolve.

## Limits

Ninety entrants over ten seasons is a small panel and most of the differences
against the previous rule are unresolved, which is a claim of no harm rather
than a claim of gain outside the outside-into-Championship cohort. The source
feature is a division-relative season summary, not a filtered latent state,
because a filtered state across divisions needs a common scale that the M9
hierarchy already failed to establish. Championship xG does not exist in this
archive, so both sides of the lower boundary are goals only. League One itself
is not in the archive: its entrants are described by a transition intercept and
their own Championship memory, and nothing this pass can do would give them a
source term. The memory timescale is shared across transitions and dimensions
and its posterior is diffuse; a larger panel could resolve it. Between-dimension
transition covariance is estimated from standardized residuals with shrinkage,
not jointly with the coefficients. Simulation does not share entry-prior
parameter draws across entrants in the same season.

Promoting this from the research parent to the published surface is a separate
step. Retained M5 and M7 season forecasts and the published projection will move
on their next rebuild, and a formal operational switch should be decided on a
rerun of the match and season scoreboard, not on this comparison alone.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_entry_prior.py \
  --output runs/entry-prior-v2 --simulations 4000
uv run python scripts/report_entry_prior.py runs/entry-prior-v2
OPENBLAS_NUM_THREADS=1 uv run --extra research pytest -q
uv run ruff check .
```
