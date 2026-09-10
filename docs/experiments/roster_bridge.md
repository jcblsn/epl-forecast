# Known-minutes roster bridge

Gate 3 of the [architecture work plan](../architecture_next_phase.md) is complete
and negative. An attacking-only known-minutes roster delta, applied to fixed M2
and M7 pre-match distributions, improves neither baseline. The failure is a
representation failure, not an estimation failure: no coefficient choice for this
design could have improved either baseline on the evaluation window.

The mapping stays parked. The frozen
[portable player interface](../portable_player_interface.md) is unaffected; this
result rejects one bridge from that interface to team scoring rates, not the
interface or the player evidence behind it.

## Design

`research/roster_bridge.py` and `scripts/evaluate_roster_bridge.py` fit

```text
log(rate*) = log(rate_base) + B [P(actual target minutes) - P(recent reference roster)]
```

on the exact saved M2 and M7 forecast distributions. B is two coefficients, no
intercept, ridge 1, fitted by a chronological Poisson mean estimating equation.
Baseline states are held fixed; deltas affect own-team attack only. There is no
player defence, no player Tilt and no lineup forecasting.

P carries the frozen shooting and creation traits. Traits, uncertainty and
reference exposure use only evidence eligible at each cutoff. Actual target
identities and minutes are an explicitly nondeployable oracle input; no target
process statistic becomes a predictor. The reference roster averages the previous
eight eligible team matches, requiring at least three. Scoring begins on
2024-08-01 after at least 200 training fixtures, giving 223 scored cutoffs and no
skipped cutoff.

Reconstruction covered all 1,140 saved baseline matches with maximum error
8.9e-16 against the original scores. One fixture is excluded because both
attacking traits require an eligible nonzero process population. The run uses
expected traits as plug-in inputs and exports the trait-variance audit without
integrating it into forecasts.

## Chronological result

760 fixtures, paired differences with calendar-week bootstrap 95% intervals.
Positive is worse than the fixed baseline. Full Brier, per-cutoff mappings and
per-case scores are in [bridge_summary.json](roster_bridge/bridge_summary.json)
and [bridge_predictions.csv.gz](roster_bridge/bridge_predictions.csv.gz).

| Slice | Fixtures | M2 outcome loss | M2 difference | M7 outcome loss | M7 difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 760 | 1.00591 | +0.00178 [-0.00038, +0.00393] | 1.00048 | +0.00108 [-0.00052, +0.00278] |
| Transfer | 110 | 0.97116 | +0.00372 [-0.00271, +0.01057] | 0.98071 | +0.00132 [-0.00494, +0.00766] |
| Injury | 718 | 1.00279 | +0.00195 [-0.00029, +0.00406] | 0.99727 | +0.00120 [-0.00046, +0.00285] |
| Large lineup change | 740 | 1.00875 | +0.00179 [-0.00046, +0.00404] | 1.00298 | +0.00114 [-0.00056, +0.00293] |
| Opening | 100 | 0.97451 | -0.00195 [-0.00716, +0.00362] | 0.97811 | -0.00068 [-0.00551, +0.00417] |
| Promoted | 216 | 0.91318 | +0.00105 [-0.00207, +0.00407] | 0.92490 | +0.00074 [-0.00260, +0.00415] |

Every interval includes zero. Every central estimate is a degradation except the
opening slice, which is the smallest slice and reverses sign on score NLL
(+0.00173 for M2, +0.00400 for M7). Score NLL degrades on both baselines in every
other slice. This is not a one-baseline-only improvement: neither baseline
improves, so the plan's alternative diagnosis applies.

Applied adjustments are small. The fitted log-rate shift has standard deviation
0.030 for M2 and 0.026 for M7, with maximum absolute value 0.166. Chronological
coefficients are weakly identified and unstable in sign: the shooting coefficient
averages -0.087 (M2) and -0.134 (M7) against an average standard error near 0.14,
while the in-sample optimum for both baselines is positive. The design itself is
well conditioned throughout, rank 2 with condition number between 2.04 and 2.37,
so the instability is an absence of signal rather than collinearity.

## Identification and representation check

[Research judgment](../research_principles.md) calls for an identification and
representation check when a channel fails with high-information inputs and no
oracle gain. `scripts/diagnose_roster_bridge.py` writes
[representation_audit.json](roster_bridge/representation_audit.json).

The ceiling test refits B in sample on the evaluation window itself. Nothing
chronological can beat a fit that already saw its own targets, so this bounds
every mapping on this design.

| Model | In-sample optimum B | Standard error | Total log-likelihood gain | Per fixture |
| --- | --- | --- | ---: | ---: |
| M2 | (+0.087, +0.108) | (0.141, 0.249) | 0.42 | 0.00056 |
| M7 | (+0.010, +0.018) | (0.138, 0.244) | 0.01 | 0.00001 |

Across 1,520 team-matches the entire attainable gain is 0.42 and 0.01 nats. Both
coefficients are well under one standard error from zero, and a permutation null
that breaks the roster-to-fixture link is not rejected (p = 0.63 for M2, p = 0.99
for M7). Pearson residual correlations with the delta are +0.022 and +0.026 (M2)
and +0.011 and +0.011 (M7). The oracle roster delta carries no measurable
information about the goals these baselines missed.

The contrast is the likely cause. Player identity is still present in the
weighted reference vector; what averaging over eight matches does is diffuse the
reference across so many players that ordinary rotation registers as a large
personnel change. The delta therefore measures routine rotation rather than the
composition discontinuity the architecture cares about. Median personnel change
is 3.1 player match
equivalents, and 87.4% of team-matches already exceed the plan's two-equivalent
threshold. That is why the required large-lineup-change slice is 97.4% of
fixtures and the injury slice 94.5%: both are retained as specified, and both are
non-discriminating under an eight-match average reference. Only the transfer
(14.5%), promoted (28.4%) and opening (13.2%) slices separate a distinct
population.

Stratifying by personnel change is consistent with dilution but does not
establish a signal.

| Minimum change | Team-matches | M2 B | M2 gain | M2 p | M7 B | M7 gain | M7 p |
| ---: | ---: | --- | ---: | ---: | --- | ---: | ---: |
| 0 | 1520 | (+0.09, +0.11) | 0.42 | 0.632 | (+0.01, +0.02) | 0.01 | 0.985 |
| 3 | 808 | (+0.00, +0.07) | 0.04 | 0.963 | (-0.07, -0.04) | 0.12 | 0.873 |
| 4 | 297 | (+0.17, -0.47) | 0.87 | 0.390 | (+0.17, -0.69) | 1.66 | 0.133 |
| 5 | 82 | (+0.96, +0.08) | 2.95 | 0.035 | (+0.90, -0.19) | 2.63 | 0.070 |

The shooting coefficient turns positive and large only in the 5.4% of
team-matches with the largest personnel change. Treat this as exploratory only.
It is in-sample, on a threshold chosen after seeing the data, across eight
model-by-threshold comparisons, on 82 team-matches, and the creation coefficient
changes sign between adjacent strata. It is a direction for a future contrast,
not evidence.

## Decision

Gate 3 is closed with a structurally inadequate mapping and no improvement on
either baseline. This is negative evidence about this contrast, not about the
player-information hypothesis: the diagnosis says the tested reference measured
ubiquitous rotation rather than the composition discontinuity the architecture
cares about.

Under the research principles the channel earns one bounded, materially different
second formulation against a sharper contrast: an identity-preserving normal-XI
or core-roster reference instead of an eight-match average, evaluated on a
genuinely discontinuous population. That formulation is not started here and does
not block Gate 4. It should wait until the cross-division club-state results are
understood, because those define what the club state is already meant to have
absorbed and give the bridge a cleaner baseline. Gate 6, which is conditional on
bridge evidence, stays closed until such a contrast produces some.
