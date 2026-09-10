# MVP discovery sprint

This compact retrospective sprint asks where residual signal is large enough to
justify work after the MVP. It reuses the 1,140 matched M2/M5/M7 and market
forecasts from 2023/24–2025/26, the frozen portable-player snapshot, and the
existing promoted-cohort transition evidence. These are discovery results. Oracle
inputs and flexible specifications identify ceilings; they do not support
deployment claims.

## Core-XI player contrast and team xG

The revised player test replaces the diffuse eight-match average with an
identity-preserving normal XI: the eleven players with the most minutes in the
prior eight eligible matches, each assigned 90 reference minutes. Actual target
identities and minutes remain an oracle. A two-trait shooting/creation contrast is
fitted before 2024/25 and evaluated on 1,520 later team-matches.

| Parent | Baseline team-xG residual MSE | Core-XI MSE | Reduction | Residual correlation |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.10052 | 0.09984 | 0.67% | 0.088 |
| M7 | 0.09702 | 0.09675 | 0.28% | 0.072 |

The sharper identity contrast carries only a very small out-of-time team-process
signal even with actual minutes. Its average change is still 3.24 player-match
equivalents, so a future representation could improve the contrast further, but
the observed ceiling does not justify building or optimizing another goal-forecast
bridge now. The [machine-readable result](discovery_core_roster/summary.csv) and
[manifest](discovery_core_roster/manifest.json) preserve the test.

## Championship-to-Premier-League transition

The existing simple promoted-cohort map already answers the first descriptive
question. PL attack is approximately `-0.380 + 0.539 × Championship attack`, with
slope SD 0.317. PL defence is approximately
`-0.292 + 0.074 × Championship defence`, with slope SD 0.250. Cohort residual SDs
are 0.074 and 0.102. The samples are small, but raw unit-slope persistence is the
wrong default, especially for defence. The empirical map supports shrinkage toward
the promoted population and preserves the useful xG observation channel; it does
not yet earn another full dynamic hierarchy. The retained
[transition table](cross_division/promotion_slope.json) is the current prior-scale
evidence.

## Low-score correction

A one-parameter Dixon-Coles correction was fitted on 760 fixtures through 2024/25
and applied unchanged to 2025/26. Negative rho adds mass to 0–0 and 1–1 and removes
mass from 1–0 and 0–1 while conserving total H/D/A probability.

| Parent | Fitted rho | H/D/A loss change | Score NLL change | Evaluation-oracle H/D/A ceiling |
| --- | ---: | ---: | ---: | ---: |
| M2 | -0.017 | -0.00079 | -0.00149 | -0.00398 |
| M7 | -0.019 | -0.00110 | -0.00166 | -0.00541 |

The chronological gain is real in direction but very small. Refitting directly on
the evaluation season chooses much stronger draw inflation and reaches a
0.004–0.005 ceiling, showing that the miss varies materially across time. Keep
independent Poisson in the MVP and investigate the stability and conditioning of
the low-score miss before confirmation. The saved
[comparison](discovery_sprint/low_score.csv) supplies scale without imposing a
significance gate.

## Structural versus market disagreement

The most repeatable disagreement is draw allocation. Across all 1,140 fixtures,
market-minus-M7 draw probability correlates +0.379 with structural entropy and
-0.214 with expected total goals. A six-feature regression fitted through 2024/25
explains 15.0% of draw disagreement in 2025/26, versus 6.5% for home and 6.2% for
away disagreement. Quality gap and expected goal difference explain part of the
side allocation; M7 uncertainty contributes mainly to draw disagreement.

This suggests that markets respond to low-total and hard-to-separate fixtures in a
way the structural score law only partly captures. It is a diagnostic direction,
not a reason to assimilate prices into club states. The
[correlations](discovery_sprint/market_disagreement.csv) and
[chronological regressions](discovery_sprint/market_disagreement_models.csv) retain
the evidence.

## Flexible scouting model

A regularized multinomial scout combines M2, M5 and M7 probabilities, nonlinear
differences, expected goal level and gap, state uncertainty, Quality and Tilt. It
fits on strictly earlier seasons and predicts 2024/25 and 2025/26 without using
markets.

| Forecast | H/D/A log loss | Brier |
| --- | ---: | ---: |
| M2 | 1.00591 | 0.60209 |
| M5 | 1.00937 | 0.60460 |
| M7 | 1.00048 | 0.59772 |
| Flexible scout | 1.01590 | 0.60808 |
| Pre-closing market | 0.99290 | 0.59446 |

The scout trails M7 by 0.01542 and is worse in both evaluation seasons. The
information already represented in these structural artifacts does not hide a
0.005–0.01 nonlinear match-accuracy gain accessible to this model. This lowers the
expected value of a broad architecture build from the same inputs. The
[pooled](discovery_sprint/scouting_summary.csv) and
[per-season](discovery_sprint/scouting_by_season.csv) comparisons are retained.

## Decision

No substantial model family is earned by this sprint. Continue the M7 structural
MVP and market-assisted near-term arm. Keep independent Poisson. The most useful
next discovery work is a season-stability analysis of the low-score/draw miss and
the market-disagreement features, followed by confirmation only if a stable
mechanism approaches the observed oracle ceiling. The core-roster and compression-
state implementations remain roadmap options whose current measured ceilings are
too small or uncertain to put on the MVP critical path.
