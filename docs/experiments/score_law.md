# One shared Gamma match-intensity score law

Gate 5 of the [architecture work plan](../architecture_next_phase.md) is complete
and negative. Adding one shared Gamma match intensity to a fixed pre-match state
does not improve score likelihood, H/D/A forecasts or season products. The
chronological fit drives the tempo shape to its upper bound at every cutoff,
which is the independent Poisson control.

The failure is not an estimation failure. Refitting the single shape in sample on
the evaluation window itself, every finite shape loses likelihood on all three
baselines. The residual the family would have to explain has the opposite sign:
these baselines already predict more score spread than the window realized, and
almost none of the observed home/away covariance survives conditioning on the
state.

## Design

`research/score_law.py` and `scripts/evaluate_score_law.py` apply two score laws
to identical saved pre-match distributions. The control is the independent
Poisson mixture already used by each baseline. The candidate multiplies both
teams' rates by one Gamma(k, 1/k) match intensity, leaving the state untouched:

```text
H, A | state, T  ~  Poisson(T * rate_home), Poisson(T * rate_away),  T ~ Gamma(k, 1/k)
```

The single shape k is refit at every cutoff by maximizing the score likelihood of
strictly earlier fixtures, searched over [1, 10,000] in log scale. Nothing else
changes: no restated state, no new observation, no outcome-level tuning.

The three saved baselines are M2 attack-defense, the M5 centered Poisson control
and M7 xG. All three record an independent-Poisson score law, so the comparison
is a clean one-mechanism switch. M7 in particular sets `dispersion = None` by
construction, because its opportunity thinning implies marginal independent
Poisson goals. Reconstruction covered all 1,140 saved matches per baseline with
maximum error 1.8e-15 against the original scores. Scoring begins on 2024-08-01
after at least 200 training fixtures, giving 223 scored cutoffs, no skipped
cutoff and 760 scored fixtures per baseline.

## Chronological result

760 fixtures per baseline, paired differences with calendar-week bootstrap 95%
intervals over 72 blocks. Positive is worse than the Poisson control. Per-cutoff
shapes and per-case scores are in [summary.json](score_law/summary.json) and
[predictions.csv.gz](score_law/predictions.csv.gz).

| Baseline | Score NLL | Difference | Outcome log loss | Difference |
| --- | ---: | ---: | ---: | ---: |
| M2 | 2.93091 | +1.21e-05 [-1.98e-06, +2.65e-05] | 1.00591 | -2.12e-06 [-4.50e-06, +1.44e-07] |
| M5 control | 2.92894 | +1.70e-05 [+4.15e-06, +3.04e-05] | 1.00937 | -2.42e-06 [-4.87e-06, -1.26e-07] |
| M7 | 2.93079 | +1.21e-05 [-1.97e-06, +2.68e-05] | 1.00048 | -2.88e-06 [-5.28e-06, -6.33e-07] |

Brier differences are the same size and sign as log loss: -1.15e-06, -1.25e-06
and -1.36e-06. Every difference is three orders of magnitude below the effects
the earlier gates reported, because the fitted law is the control. The shape sits
at the upper bound at 223 of 223 cutoffs for all three baselines, with median
fitted values of 9999.63, 9999.65 and 9999.65. The M5 control's score NLL
interval excludes zero, as do the M5 and M7 log loss and Brier intervals; at
1e-05 nats none of these are decision-relevant quantities.

## Identification and representation

The boundary is a statement about the family, not the estimator. Refitting the
shape in sample on the 760 scored fixtures reaches the same bound, and the
attainable in-sample likelihood gain is negative at every shape tried, rising
toward zero only as the tempo vanishes. Gains in nats over the whole window:

| Shape k | 2 | 5 | 10 | 20 | 50 | 100 | 500 | 2,000 | 10,000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| M2 | -127.75 | -43.33 | -17.60 | -7.11 | -2.29 | -1.04 | -0.19 | -0.05 | -0.01 |
| M5 control | -131.61 | -46.58 | -19.94 | -8.56 | -2.96 | -1.39 | -0.26 | -0.06 | -0.01 |
| M7 | -125.24 | -42.32 | -17.21 | -6.98 | -2.27 | -1.03 | -0.19 | -0.05 | -0.01 |

No shape could have helped, so no chronological shape choice was ever available.

The moments say why. A shared Gamma tempo can only add score dispersion and
positive home/away dependence, and both are already too large:

| Baseline | Predicted total variance | Observed | Predicted residual covariance | Observed | At k = 20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| M2 | 2.950 | 2.601 | 0.000 | +0.007 | +0.102 |
| M5 control | 3.084 | 2.569 | -0.011 | +0.001 | +0.092 |
| M7 | 3.235 | 2.654 | -0.005 | +0.035 | +0.110 |

Observed columns are mean squared residuals about each baseline's own predicted
means, so they include that baseline's mean miss; these baselines overpredict
total scoring on this window, with predicted total means of 2.950, 2.978 and
3.149 against 2.842 observed. The raw window is underdispersed relative to
Poisson on its own terms as well: total goals have sample mean 2.842 and sample
variance 2.547, where an independent Poisson law at that mean implies 2.842.

Raw home and away goals correlate -0.092 across the 760 fixtures, and that
negative dependence is what the states are for. Once each baseline's predicted
means are removed, the residual covariance is +0.007, +0.001 and +0.035 against
the +0.09 to +0.11 that a shape of 20 would impose. The one mechanism this
family offers is the one the data least need.

## Tail events

Predicted mass against observed frequency, with the fixed reference shape 20
shown alongside. At the chronologically fitted shape the two laws agree to four
decimals on every event, so only the reference column moves.

| Event | Observed | M2 Poisson | M2 at k = 20 | M7 Poisson | M7 at k = 20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Draw | 0.2592 | 0.2287 | 0.2353 | 0.2175 | 0.2239 |
| Scoreless | 0.0566 | 0.0559 | 0.0673 | 0.0464 | 0.0572 |
| Six or more goals | 0.0526 | 0.0833 | 0.0962 | 0.1050 | 0.1186 |
| Both teams score | 0.5671 | 0.5555 | 0.5442 | 0.5842 | 0.5718 |

Across all 2,280 scored pairs the fitted law and the control differ by at most
1.7e-05 in any H/D/A probability and 1.4e-03 in any single score NLL.

There is a real tail miss here, and it is not the score law's to fix. Draws are
underpredicted by 3.1 points for M2 and 4.2 for M7, while six-or-more-goal
matches are overpredicted by 3.1 and 5.2 points. A shared tempo improves the
draw share slightly and makes the high-scoring tail and the scoreless share
worse by more. The likelihood prices that trade and rejects it. Correcting these
tails requires less total-score dispersion with more draw mass, which no
positive shared tempo can express.

## Season products

The matched [uncertainty budget](uncertainty_budget.md) already scores this same
switch at a fixed shape of 20 over 11 seasons, five origins and 220 club-seasons,
adding shared tempo to the evolving goals state and changing nothing else.
Preseason differences, candidate minus comparator, with intervals resampling
whole seasons:

| Season measure | Difference [95% interval] |
| --- | ---: |
| TRPS | +0.00012 [-0.00043, +0.00066] |
| Points CRPS | +0.01024 [-0.02444, +0.04772] |
| Points SD | -0.08638 [-0.10473, -0.06652] |
| 90% width | -0.34091 [-0.44091, -0.24091] |
| 90% coverage | -0.455 pp [-1.364, +0.000] |

Title, top-four and relegation Brier intervals all span zero, at every origin.
Preseason exact score NLL is worse by +0.00876, and that holds under iid-match,
calendar-week and season-cluster intervals alike, the season interval being
[+0.00562, +0.01200].

The direction is consistent with the moments above. A shared tempo moves both
teams' scoring together, which shrinks the goal-difference spread that season
points depend on. Points distributions narrow and 90% coverage falls, on a
product whose coverage was already short of nominal. At the shape this gate
actually fits, season paths are indistinguishable from the control, so nothing
was gained to offset that.

## What this rejects

This rejects one score law, not dependence or overdispersion as concerns. The
tested family has a single positive parameter that can only widen scores and
couple the two teams positively. The evidence says this window wants the
opposite, and that the visible tail miss is in the draw and high-scoring shares
rather than in the marginal spread.

Independent Poisson remains the control and the retained score law. Per the
plan's stopping condition, no further complexity follows from this gate: a
second score-law formulation would need a mechanism that can produce
underdispersion or draw inflation, and would need its own stated hypothesis,
cutoff and stopping condition before running. Gate 5 was independent of the
Gate 4 state outcome and does not change it.
