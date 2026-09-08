# Matched uncertainty budget

## Decision

Current-state uncertainty earns permanent support for early-season points
forecasts. Future innovation uncertainty does not earn adaptive elaboration in
this batch. A separate season-dependence layer around unchanged M2 match
probabilities is a credible product architecture: it improves preseason points
CRPS and TRPS without changing match forecasts. This is historical development
evidence, not a prospective production-promotion decision.

M2 remains the operational match benchmark; M7 remains the structural research
parent. Retain the matched switches as diagnostic infrastructure. Do not add M9,
adaptive team-specific dynamics, or a new score law on these results.

## Design and evidence

`runs/uncertainty-ladder-v1` covers eleven PL seasons, 2015/16–2025/26, at
preseason/MW6/MW12/MW19/MW30, with 2,000 paths per cell. The immutable input is
`runs/research-ready-v1-initial/manifest.json`. There are 17,600 club-season-origin
rows and 215,536 match-origin rows, including calibrated aliases. Repeated
origins are not independent matches. The report has 400 season and 300 match
comparisons, with no missing pairs.

The main simulation started at clean commit `5678a89`. The manifest retains the
exact execution surface. Its SHA-256 is
`cdbd5ac707444b858489ca58d35c1c1ea3e2c1c9d7ef7572ef01de0e536ccdee`.
`attribution.json` SHA-256 is
`bfa19f60a2dfa7a2e58c22c95321b8d1d559ac523767e4c576126ed7040a718d`;
it records hashes for the scored inputs and the reporting execution separately.

The matched goals variants share fitted population-state means, initialization,
information, and the conditional independent-Poisson score law. Posterior draws,
deterministic mean reversion, future innovations and conditioning current
promoted coordinates are distinct switches. Conditioning preserves means but
removes associated joint covariance; it is not a refit with a different entry
prior. The xG variant refits observations at the same fixed dynamics and p=0.2.
The gamma-score variant retains the goals state and adds shared match tempo at
dispersion 20. These switches are conditional comparisons, not an additive or
order-independent decomposition.

The M2 copula preserves each match's entire independent-Poisson distribution.
Its dependence weight is selected from 0/0.1/0.25/0.5 using only earlier seasons'
points CRPS at the same origin; the first season uses zero. No market prices
enter fitting or calibration. M4/M5/M7 are richer end-to-end benchmarks, not
matched single-mechanism switches.

## Preseason uncertainty budget

Differences are candidate minus comparator. Negative CRPS is better. Intervals
resample whole seasons; coverage changes below are percentage points.

| Added mechanism | Points CRPS difference [95% interval] | 90% width change | Coverage change |
| --- | --- | ---: | ---: |
| Posterior versus fixed state | −0.158 [−0.242, −0.087] | +7.41 points | +9.09 pp |
| Mean reversion versus posterior | +0.052 [−0.015, +0.120] | −0.57 | −1.82 pp |
| Innovations versus mean reversion | −0.008 [−0.041, +0.019] | +1.62 | +2.27 pp |
| Current promoted-state uncertainty | −0.028 [−0.076, +0.021] | +1.15 | +3.18 pp |
| xG observations versus evolving goals | +0.063 [−0.237, +0.366] | −1.29 | −2.27 pp |
| Gamma score law versus Poisson | +0.010 [−0.024, +0.048] | −0.34 | −0.45 pp |
| Calibrated M2 dependence versus M2 | −0.199 [−0.345, −0.078] | +10.32 | +12.27 pp |

The posterior gain continues at MW6, −0.105 [−0.173, −0.041], and MW12,
−0.053 [−0.091, −0.018]. It is not resolved at MW19/MW30. Future innovations'
CRPS and TRPS intervals span zero at every origin. Increased coverage alone is
not enough to justify a more elaborate transition model.

Promoted-state uncertainty has a small MW6 CRPS gain, −0.021
[−0.037, −0.004], but this all-club comparison does not determine the optimal
promoted prior mean or variance. That requires the separate transition test.

xG is not an early-season widening mechanism. It gives a later MW30 points
CRPS gain, −0.068 [−0.118, −0.022], while the earlier-origin intervals span zero.
This is consistent with retaining M7 as the research parent, not declaring xG
universally useful or useless. The [information-value report](information_value.md)
addresses residual sensor value with a different, explicitly limited target.

All preseason title/top-four/relegation Brier comparison intervals span zero.
Posterior uncertainty's preseason TRPS interval also spans zero. The strongest
early matched evidence is for points distributions, not every forecast product.

## Split-product architecture

| Preseason model | Points CRPS | 90% coverage | 90% width |
| --- | ---: | ---: | ---: |
| M2 | 6.768 | 72.3% | 24.75 |
| M2 + calibrated dependence | 6.570 | 84.5% | 35.07 |
| M4 | 6.475 | 88.2% | 34.99 |
| M5 | 6.529 | 86.4% | 33.15 |
| M7 | 6.576 | 84.5% | 32.03 |

Calibrated M2 improves preseason TRPS by −0.00228
[−0.00512, −0.00009]. Its points CRPS gain persists through MW12, but is not
resolved at MW19/MW30. Match log loss and exact-score NLL differences from M2
are exactly zero at every origin by construction and in the retained scores.

Preseason CRPS differences from calibrated M2 are M4 −0.095
[−0.436, +0.252], M5 −0.040 [−0.366, +0.254], and M7 +0.006
[−0.553, +0.466]. No richer model demonstrates a reliable preseason advantage
over the split product here. At MW30, M4 and M5 are slightly worse on both
points CRPS and TRPS; M7's differences remain unresolved. Calibration still
falls short of nominal coverage, so this is not a claim that dispersion is solved.

## Match dependence and score law

The report provides iid-match, calendar-week and season-cluster intervals
separately at each origin. For example, preseason M7 minus calibrated M2 exact
NLL is −0.00960: iid interval [−0.01763, −0.00198], weekly
[−0.01785, −0.00103], but season [−0.02531, +0.00479]. A favorable fine-grained
interval is not robust evidence of superiority across seasons. These are
origin-conditioned forecasts of all remaining fixtures, not the established
daily-refit operational match comparison.

The gamma-score variant worsens preseason exact NLL by +0.00876; all three
dependence intervals exclude zero, including season [+0.00562, +0.01200]. It
does not improve preseason outcome log loss or season proper scores reliably.
Do not promote that alternative score law.

## Limits and next action

Eleven seasons give limited tail-event precision. The many mechanism/product/
origin comparisons are descriptive development evidence, with no multiple-test
correction or nested model-selection claim. Monte Carlo error is not separately
integrated into the intervals. Fixed global dynamics and the chosen score-law
setting are not exhaustive searches over possible mechanisms.

Retrospective final fixture schedules and next-day result availability are
explicit research assumptions; retained archive retrieval times are not proof
of contemporaneous availability. No late injury, lineup-time, Championship
promotion probability, or market-assisted capability is evaluated here.

Complete the promoted-population/results/process initialization comparison.
If roster data support a bounded offseason discontinuity test, keep it at that
boundary; this ladder does not authorize expanding adaptive within-season
dynamics. Keep detailed player effects behind the requested oracle gate.
