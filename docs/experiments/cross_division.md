# Cross-division club states

Gate 4 of the [architecture work plan](../architecture_next_phase.md) is complete
and negative on forecasts. M9 implements one bounded dynamic-state candidate: a
single club-state hierarchy spanning the Premier League and the Championship, in
which a club keeps its two-dimensional latent scoring state when it is promoted
or relegated. The state mechanics check out; the forecasts do not, and a synthetic
regime with a planted strength gap reproduces the exact failure seen on real data.

M2 remains the operational benchmark and M7 the retained xG benchmark. M9 is
parked as a forecasting candidate. Its diagnosis is specific enough to name the
next formulation.

## Candidate

`models/cross_division.py` holds each club's Quality/Tilt state across divisions.
The leading league block carries a shared scoring level, a home advantage, a
Championship scoring-level offset and a Championship home offset. Premier League
fixtures load only the first two, so the Premier League is the reference division
and the Championship offsets are identified by the clubs that cross. All four
evolve as slow random walks, so home advantage may change. Inference is the
existing daily joint Laplace Gaussian filter, sequential and with an explicit
Gaussian posterior.

The division scoring level is added to both teams' log rates. It therefore answers
whether Championship matches are higher or lower scoring than otherwise comparable
Premier League matches. It does not measure how much weaker a typical Championship
club is. That common strength scale comes from elsewhere: a club is drawn from the
population prior once, when it first appears in either division, and never again,
so crossings link two otherwise separate networks of pairwise comparisons. This is
the substantive change, since the retained models instead reset a promoted club to
an empirical-Bayes entry prior from the promotion bridge.

`CrossDivisionXG` adds team xG as a noisy measurement of the same process, reusing
the M7 opportunity likelihood: goals are the Binomial thinning of a Poisson
opportunity process and xG its Gamma measurement. xG never double-counts goals and
is never forced to equal an additive player total.

The hierarchy's sensors are asymmetric. Understat covers 4,590 of 6,110 Premier
League matches in this data, 75.1%, and 0 of 8,898 Championship matches. Every
Championship update is goals-only, so a promoted club always arrives carrying a
state that has never seen xG. "Cross-division xG" means xG on one side of the
hierarchy only.

## Goals-only mechanics

[state_mechanics.json](cross_division/state_mechanics.json) generates both
divisions from one known club scale and a known scoring level, then refits.
Thirty replicates.

| Model | Level error | Level SD | Level coverage | Home coverage | Quality correlation | Quality MSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Goals only | +0.016 | 0.090 | 1.00 | 0.90 | 0.925 | 0.0076 |
| Goals and xG | +0.017 | 0.072 | 1.00 | 1.00 | 0.960 | 0.0044 |

Both observation models recover the planted scoring level and home advantage with
at least nominal 95% coverage, and team xG sharpens the state as intended.
Observed transitions, not the prior, identify the common scale: raising crossings
per season from zero to five lowers the level posterior SD from 0.104 to 0.084 and
its root mean squared error from 0.117 to 0.067.

Attack/defence and Quality/Tilt are one state in two coordinates. Rotating the
fitted state and design reproduces the forecast moments to 5.6e-17 and 1.7e-18
maximum absolute difference. This is a coordinate choice, not a second model
family. The same holds for centering: on real data the uncentered bridge control
reproduces the centered control's scores exactly.

## The regime that matters: a planted cross-division strength gap

Recovering a scoring-level difference is the easier problem. The harder one plants
an absolute strength difference between the two club populations while each club
keeps its latent identity across the divide, then asks whether a crossing club's
first forecasts in its new division are calibrated. Errors below are in true log
rate, over the first ten matches after each transition, 8 replicates.

| Quality gap | Model | Promoted error | Relegated error |
| ---: | --- | ---: | ---: |
| 0.00 | Goals only | -0.0044 (SE 0.0056) | -0.0149 (SE 0.0058) |
| 0.00 | Goals and xG | +0.0015 (SE 0.0041) | +0.0247 (SE 0.0044) |
| 0.45 | Goals only | +0.0465 (SE 0.0059) | -0.0114 (SE 0.0067) |
| 0.45 | Goals and xG | +0.0570 (SE 0.0042) | +0.0162 (SE 0.0051) |

With no gap, promoted forecasts are unbiased. With a planted gap they overstate
promoted clubs by roughly eight to fourteen standard errors, while relegated clubs
stay close to zero. Note that in this generator each club's true strength is
unchanged by crossing, so a correct model would show no bias at either gap. The
bias appears because an additive scoring level cannot absorb an absolute
population difference: part of the Championship population's weakness is
attributed to the scoring environment, leaving carried club states too strong when
they enter the Premier League. That is a property of the parameterization, not of
the data.

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
| M9 goals only | 0.97104 | 0.57653 | 3.03172 |
| M9 goals and xG | 0.96062 | 0.56874 | 3.01777 |

The uncentered bridge control isolates the change. It shares M9's coordinates,
dynamics, score law and training competitions, and differs only in resetting a
promoted club to the promotion bridge instead of carrying its state.

| Slice | Fixtures | M9 goals − bridge control | M9 xG − M7 |
| --- | ---: | ---: | ---: |
| All | 760 | +0.01413 [+0.00890, +0.01943] | +0.00778 [+0.00454, +0.01148] |
| Promoted | 108 | +0.05179 [+0.03608, +0.06718] | +0.02717 [+0.01595, +0.04161] |
| Established | 652 | +0.00789 [+0.00196, +0.01434] | +0.00456 [+0.00131, +0.00851] |
| Opening five | 101 | +0.03350 [+0.02268, +0.05173] | +0.02618 [+0.01693, +0.03889] |

M9 is worst on promoted clubs, the population cross-division persistence was meant
to serve, and by a factor of roughly four against its whole-population loss. This
is the outcome that matters: a diffuse aggregate change would be uninformative,
but a large, consistent transition-slice loss says the hierarchy is not solving
the cross-division problem. Within M9, adding team xG gains -0.01042 [-0.01856,
-0.00210]. The observation channel works; the state structure is what fails.

## Why carrying the state fails

Carrying a state across the divide asserts that a promoted club's Premier League
strength equals its Championship strength plus one shared scoring level: a slope
of one in both dimensions. The retained promotion bridge estimates that slope from
realized promoted cohorts.
[promotion_slope.json](cross_division/promotion_slope.json), fitted on 42 cohorts
through 2024/25, gives an attack slope of 0.539 (SD 0.317) and a defence slope of
0.074 (SD 0.250), with intercepts -0.380 and -0.292.

Unit slope is 1.5 standard errors away in attack and 3.7 away in defence. The
Premier League transition is a compression toward the promoted-club population,
strongly so in defence, not a translation. The attack estimate alone would be weak
evidence; the defence estimate is not.

The synthetic gap regime shows the same failure arising from the parameterization
even when club identity truly is preserved, so the two mechanisms compound: real
promoted clubs both compress and are mis-attributed by an additive-only level.

Two further costs follow. Championship states never receive xG, so promoted clubs
arrive with the least-informed states in the hierarchy. And a shared league level
ties the divisions together, so misplaced promoted-club states move established
club forecasts too, which is visible in the established slice.

## Identification: read the league block with care

M9 inherits the uncentered Quality/Tilt filter. Tilt enters both teams' rates with
the same sign, so the population mean of club Tilt can trade off against a league
scoring level. The repository built `CenteredQualityTiltFilter` to remove exactly
this ambiguity, and M9 adds a second scoring-level parameter without it. The
zero-centered dynamic priors keep the posterior proper, so this is weak
identification rather than non-identifiability, but it makes the Championship
scoring level more prior-dependent than its posterior SD suggests.

[scoring_level_identification.json](cross_division/scoring_level_identification.json)
measures it on real data at a 2025-07-01 cutoff, refitting over a 27-point grid of
the division-level prior, the initial club prior and the Tilt innovation scale.

| Quantity | Range across the grid | Relative to its posterior SD |
| --- | ---: | ---: |
| Championship scoring level, goals only | 0.0617 | 1.25 |
| Championship scoring level, goals and xG | 0.0702 | 1.49 |
| Home advantage, goals and xG | 0.0003 | negligible |

The movement is driven almost entirely by the Tilt prior, exactly where the
identification argument points: with xG, the level runs from -0.221 at a Tilt
innovation scale of 0.035 to -0.153 at 0.140, monotonically. The division-level
and club priors move it by 0.003 or less.

So the Championship scoring level is a working evaluation coordinate, not a
settled latent quantity. Its reported posterior SD of 0.044 understates its real
uncertainty by roughly half again, and neither its value nor its trajectory should
be read substantively until the coordinate is fixed. Home advantage is not
affected: it is separately identified by the home/away contrast and moves by
0.0003 across the same grid.

## Retained results

[state_path.json](cross_division/state_path.json) refits M9 at half-year cutoffs
from 2017 to 2026 over both divisions, 61 clubs of which 34 crossed divisions.

Home advantage declines from about +0.25 in 2017 to about +0.20 in 2026, with a
minimum near +0.15. Given the identification audit above, this is the one league
quantity here worth treating as real, and a changing home advantage belongs in any
joint model. Team xG sharpens it, taking its posterior SD from 0.036 to 0.028. The
Championship home offset is +0.024 (SD 0.035), indistinguishable from zero.

The fitted Championship scoring level settles near -0.16 (SD 0.044) with xG, but
per the identification audit that number is reported as a coordinate output only.

## Decision

M9 is parked as a forecasting candidate. The concept is not refuted: the states
are identifiable from crossings, the mechanics recover known truth with at least
nominal coverage, and the xG observation channel helps. The failure is
representational and localized, and both the slope audit and the planted-gap
regime say where.

The next formulation, stated before it is run: replace the additive-only division
level with a division map that compresses club states toward the division
population, and settle the coordinate at the same time so the league-level terms
own the corresponding means and club Tilt deviations are centered. Its stopping
condition is the promoted slice and the planted-gap calibration, not
whole-population loss. Nothing here reopens the promotion bridge, which remains
the operational entry prior and is now measured rather than assumed.

Gate 5 is independent of this outcome. The home-advantage path and the xG
sharpening are retained for Gate 7's joint simulation regardless of which state
formulation carries it.
