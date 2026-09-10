# Cross-division club states

Gate 4 of the [architecture work plan](../architecture_next_phase.md) is complete
and negative on forecasts. M9 implements one bounded dynamic-state candidate: a
single club-state hierarchy spanning the Premier League and the Championship, in
which a club keeps its two-dimensional latent scoring state when it is promoted
or relegated. Mechanics check out; forecasts do not.

M2 remains the operational benchmark and M7 the retained xG benchmark. M9 is
parked as a forecasting candidate. Three of its results are retained as evidence
for later gates: the fitted division level, the home-advantage decline, and the
confirmation that noisy team xG sharpens a cross-division state.

## Candidate

`models/cross_division.py` holds each club's Quality/Tilt state across divisions
and estimates the division level separately. The leading league block carries a
shared scoring level, a home advantage, a Championship level offset and a
Championship home offset. Premier League fixtures load only the first two, so the
Premier League is the reference division and the Championship offsets are
identified by the clubs that cross. All four evolve as slow random walks, so home
advantage may change. Inference is the existing daily joint Laplace Gaussian
filter, sequential and with an explicit Gaussian posterior.

A club is drawn from the population prior once, when it first appears in either
division, and never again. This is the substantive change: the retained models
reset a promoted club to an empirical-Bayes entry prior from the promotion
bridge, while M9 carries the club's own Championship state across the divide.

`CrossDivisionXG` adds team xG as a noisy measurement of the same process, reusing
the M7 opportunity likelihood: goals are the Binomial thinning of a Poisson
opportunity process and xG its Gamma measurement. xG never double-counts goals
and is never forced to equal an additive player total. Understat covers the
Premier League only, so Championship matches update on goals alone and a promoted
club arrives carrying a goals-only state.

## Goals-only mechanics

[state_mechanics.json](cross_division/state_mechanics.json) generates both
divisions from one known club scale and a known division level, then refits.

| Model | Level error | Level SD | Level coverage | Home coverage | Quality correlation | Quality MSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Goals only | +0.025 | 0.093 | 0.97 | 0.93 | 0.925 | 0.0076 |
| Goals and xG | +0.020 | 0.073 | 0.97 | 1.00 | 0.960 | 0.0044 |

Thirty replicates. Both observation models recover the planted division level and
home advantage with approximately nominal 95% coverage, and team xG sharpens the
state as intended. Observed transitions, not the prior, identify the common
scale: raising crossings per season from zero to five lowers the level posterior
SD from 0.106 to 0.088 and its root mean squared error from 0.122 to 0.070.

Attack/defence and Quality/Tilt are one state in two coordinates. Rotating the
fitted state and design reproduces the forecast moments to 0.0 and 5.2e-18
maximum absolute difference. This is a coordinate choice, not a second model
family. The same point holds for centering: on real data the uncentered bridge
control reproduces the centered control's scores exactly.

## Matched chronological comparison

760 validation fixtures, 2023/24–2024/25. Paired differences use 28-day blocks
within seasons; positive is worse than the reference. Full slices and per-case
scores are in [matched_comparison.json](cross_division/matched_comparison.json)
and [validation_predictions.csv.gz](cross_division/validation_predictions.csv.gz).

| Model | Outcome loss | Brier | Score NLL |
| --- | ---: | ---: | ---: |
| M2 | 0.95734 | 0.56782 | 3.02700 |
| M5 centered control | 0.95692 | 0.56696 | 3.01556 |
| M5 uncentered bridge control | 0.95692 | 0.56696 | 3.01556 |
| M7 | 0.95285 | 0.56342 | 3.01052 |
| M9 goals only | 0.97105 | 0.57653 | 3.03174 |
| M9 goals and xG | 0.96063 | 0.56874 | 3.01777 |

The uncentered bridge control isolates the change. It shares M9's coordinates,
dynamics, score law and training competitions, and differs only in resetting a
promoted club to the promotion bridge instead of carrying its state. Against it,
M9 loses +0.01413 [+0.00889, +0.01944]. M9 with xG loses +0.00778 [+0.00454,
+0.01149] against M7 and +0.00328 [-0.00946, +0.01667] against M2.

Within M9, adding team xG gains -0.01042 [-0.01856, -0.00210]. The observation
channel works; the state structure is what fails.

| Slice | Fixtures | M9 goals − bridge control | M9 xG − M7 |
| --- | ---: | ---: | ---: |
| All | 760 | +0.01413 [+0.00889, +0.01944] | +0.00778 [+0.00454, +0.01149] |
| Promoted | 108 | +0.05182 [+0.03610, +0.06721] | +0.02718 [+0.01596, +0.04162] |
| Established | 652 | +0.00789 [+0.00196, +0.01434] | +0.00456 [+0.00131, +0.00851] |
| Opening five | 101 | +0.03350 [+0.02268, +0.05173] | +0.02618 [+0.01693, +0.03889] |

M9 is worst on promoted clubs, the population cross-division persistence was
meant to serve. The whole-population loss is largely that slice leaking into the
rest through a shared league level.

## Why carrying the state fails

Carrying a state across the divide asserts that a promoted club's Premier League
strength equals its Championship strength plus one shared division level: a slope
of one in both dimensions. The retained promotion bridge estimates that slope
from realized promoted cohorts.
[promotion_slope.json](cross_division/promotion_slope.json), fitted on 42 cohorts
through 2024/25, gives an attack slope of 0.539 (SD 0.317) and a defence slope of
0.074 (SD 0.250), with intercepts -0.380 and -0.292.

Unit slope is 1.5 standard errors away in attack and 3.7 away in defence. The
Premier League transition is a compression toward the promoted-club population,
strongly so in defence, not a translation. A single additive division level
cannot represent that, so M9 imports Championship club differences at roughly
twice their transferable size in attack and roughly fourteen times in defence.
The attack estimate alone would be weak evidence; the defence estimate is not,
and the promoted slice is where M9's loss concentrates.

Two further costs compound it. Understat covers the Premier League only, so a
promoted club arrives with a state that never received xG. And a shared league
level ties the two divisions together, so misplaced promoted-club states move
established-club forecasts as well, which is visible in the established slice.

## Retained results

[state_path.json](cross_division/state_path.json) refits M9 at half-year cutoffs
from 2017 to 2026 over both divisions, 61 clubs of which 34 crossed divisions.

The Championship scoring level settles near -0.16 (SD 0.044) with xG, about 15%
below Premier League scoring. The Championship home offset is +0.024 (SD 0.035),
indistinguishable from zero: home advantage does not differ materially between
the divisions. Home advantage itself declines from about +0.25 in 2017 to about
+0.20 in 2026, with a minimum near +0.15. A changing home advantage is real in
this data and worth keeping in any joint model. Team xG sharpens both league
quantities, taking the home advantage SD from 0.036 to 0.028.

## Decision

M9 is parked as a forecasting candidate. The concept is not refuted: the states
are identifiable, the mechanics recover known truth with near-nominal coverage,
and the xG observation channel helps. The failure is representational and
localized, and the slope audit says exactly where.

A second formulation is available under the
[research principles](../research_principles.md) and should be stated before it
is run: replace the additive-only division level with a division map that
compresses club states toward the division population, and check whether it
recovers the bridge control's promoted-slice performance while keeping one
persistent state per club. Its stopping condition should be that slice, not
whole-population loss. Nothing here reopens the promotion bridge, which remains
the operational entry prior and is now measured rather than assumed.

Gate 5 is independent of this outcome. The division level, home-advantage path
and xG sharpening are retained for Gate 7's joint simulation regardless of which
state formulation carries it.
