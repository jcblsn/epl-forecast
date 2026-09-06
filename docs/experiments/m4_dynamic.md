# M4: first probabilistic dynamic team-state model

The vertical slice works: a learned Championship promotion hierarchy initializes
dynamic attack/defense states, Gaussian filtering retains uncertainty, match
forecasts integrate it, and season simulation reuses a joint posterior draw
throughout each path. M2 remains the default. M4 has not demonstrated a predictive
advantage sufficient to replace it, especially early in a season.

## Rolling evidence

Daily forecasts cover all 4,180 PL matches in 2015/16–2025/26. M2 keeps its
1,095-day PL window; M4 uses expanding PL/Championship history. Promotion
coefficients use only earlier completed cohorts. Prototype dynamics settings
were fixed before this comparison; no parameter search or test-season selection
was performed. All these seasons are development evidence.

| Model | Log loss | Brier | ECE | Score NLL |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.97411 | 0.57876 | 0.01347 | 2.94152 |
| M4 posterior predictive | 0.97374 | 0.57837 | 0.01538 | 2.94388 |
| M4, promotion-cohort prior only | 0.97374 | 0.57839 | 0.01508 | 2.94370 |
| M4, fixed posterior mean | 0.97288 | 0.57797 | 0.01080 | 2.93993 |

The cohort ablation removes individual Championship performance, retaining a
learned promoted-population prior. The mean ablation keeps M4's fitted states
but omits parameter mixing in match forecasts. Individual Championship signal
adds little here; posterior mixing slightly worsens match scores. This makes
uncertainty validation a priority, even though season uncertainty is functional.

The M4-minus-M2 loss difference is −0.00038, with a descriptive 95% paired
28-day block-bootstrap interval of [−0.00329, +0.00252] (1,000 draws, 119 blocks).

| Slice | Matches | M2 loss | M4 loss |
| --- | ---: | ---: | ---: |
| Either club's first six appearances | 663 | 0.97752 | 0.98289 |
| Any promoted club | 1,188 | 0.93025 | 0.92948 |
| Promoted club's first ten appearances | 311 | 0.93498 | 0.94266 |
| Promoted club, after the first ten | 877 | 0.92857 | 0.92481 |
| Incumbents only | 2,992 | 0.99153 | 0.99131 |
| 2025/26 | 380 | 1.02649 | 1.03701 |

M4 improves loss in five of eleven seasons. Its largest improvement is 2022/23
(0.98348 versus 0.99592); its largest deterioration is 2025/26. Early-season ECE
is slightly lower, but proper scores are worse. Aggregate ECE is also worse.
The Bet365 comparison covers all 4,180 matches at loss 0.96021; its information
horizon differs and no odds enter either structural model.

## What the bridge learned

Across 45 promotion cohorts in 2011/12–2025/26, first-ten-match performance is:

| Group | Club-seasons | Points/game | Goals for/game | Goals against/game |
| --- | ---: | ---: | ---: | ---: |
| Promoted | 45 | 0.916 | 1.004 | 1.764 |
| Incumbent | 255 | 1.455 | 1.467 | 1.331 |

These are descriptive appearance averages, not opponent-adjusted causal effects.
The bridge's entry estimates adjust goals for opponent strengths using each
completed PL season as a reference. That makes them noisy entry proxies rather
than directly observed entry quality; full details are in the
[model specification](../dynamic_model.md).

The bridge available for 2026/27 estimates:

| Dimension | Intercept | Championship slope | Slope SD | Residual RMS SD |
| --- | ---: | ---: | ---: | ---: |
| Attack | −0.342 | 0.416 | 0.296 | 0.072 |
| Defense | −0.269 | 0.018 | 0.192 | 0.104 |

A 0.1 increase in Championship log attack corresponds to about 0.042 in PL
entry log attack, with substantial uncertainty. Both slopes' approximate
95% intervals include zero. Defensive carryover is particularly weak in this
first-ten-goal proxy. The reusable prior learns the promotion population and
carries source, regression and residual uncertainty; it is not a fixed penalty.

PL evidence gradually displaces the individual Championship contribution.
Across the same 33 promoted club-seasons in evaluation, the RMS difference from
the cohort-only model falls as follows:

| Prior PL appearances | Attack gap | Defense gap |
| --- | ---: | ---: |
| 0 | 0.0926 | 0.0218 |
| 10 | 0.0736 | 0.0113 |
| 20 | 0.0590 | 0.0079 |
| 37 | 0.0400 | 0.0052 |

This counterfactual difference is a sensitivity diagnostic, not a literal
posterior prior-weight. Attack differences persist for much of the season;
defense differences approximately halve within ten matches. Mean attack SD
moves from 0.152 to 0.160 over the season; defense SD falls from 0.178 to 0.150.
Learning competes with process noise, so uncertainty need not shrink monotonically.

A seeded synthetic season adds 0.7 to one club's true log attack. Twenty matches
later M4's estimated league-relative attack is 0.187 versus M2's 0.075; after
thirty it is 0.325 versus 0.176 (truth 0.415). M4 responds faster in this example,
but a single synthetic path does not establish general adaptation or interval
coverage.

## Posterior season simulation and the live defect

Using the same September 5 snapshot, 28 fixed results and 10,000 paths:

| Arsenal forecast | Points SD | Central 90% points interval | Title |
| --- | ---: | ---: | ---: |
| M4 fixed posterior mean | 7.17 | 67–90 | 44.7% |
| M4 posterior states | 9.83 | 61–94 | 39.0% |

The state is shared across matches within a season path. This broadening cannot
be obtained by independently resampling each match's marginal distribution.
Neither run includes hot evolution, transfers or lineups.

| Promoted club | Original M2 points | M4 points | Original M2 relegation | M4 relegation |
| --- | ---: | ---: | ---: | ---: |
| Hull | 61.1 | 39.1 | 0.2% | 36.0% |
| Coventry | 33.8 | 33.3 | 76.1% | 62.5% |
| Ipswich | 27.8 | 33.8 | 95.0% | 61.2% |

Hull's projection is now more plausible, without a bespoke offset. This is a
sanity check, not proof of accuracy. Current M4 state means also put Arsenal and
Manchester City at the top of defensive strength among current clubs, while all
three promoted clubs have below-reference defensive means.

A local full-history fit took about 0.9 seconds; 10,000 posterior season paths
took about 0.63 seconds. These are illustrative timings, not a runtime guarantee.

## Artifacts and next step

The [README commands](../../README.md#improve-the-model) reproduce rolling
forecasts and diagnostics. This run used `runs/m4-development`,
`runs/m4-validation`, `runs/m4-holdout` and `runs/m4-diagnostics-v2`.
The diagnostic directory contains per-match predictions, per-season scores,
calibration bins, matched markets, bridge cohorts, prior trajectories and the
synthetic response. `runs/m4-season-uncertainty.json` records the simulation
comparison. Generated data remain local and Git-ignored.

The live M4 archive is `runs/forecasts/m4-2026-09-05/`; the snapshot is
`snapshots/2026-09-05T195837.485290Z/`. It contains 352 match forecasts, 20
team-state summaries and a posterior season projection.

Continue M4 by checking the entry proxy/reference scale and uncertainty coverage,
including the omitted uncertainty in season summaries and common bridge
parameters. The two-stage approximation is deliberately limited. Keep M2 as the
default while addressing the early-season weakness; player priors, richer scoring
and hot evolution can build on this boundary when the state model supports them.
