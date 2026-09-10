# Championship entry states for relegated clubs

## Decision

Keep the current treatment. A relegated club continues to enter the Championship
on the Championship state it last held, decayed by the elapsed calendar time.
Neither a generic relegated-club prior nor an opponent-adjusted mapping from the
club's Premier League season improves its first ten Championship matches or its
season distribution, and both narrow the points interval enough to cost coverage.
The `relegation_entry` switch and `RelegationBridge` are retained as research
infrastructure, with `retained` as the default.

The addendum's suspicion was that discarding Premier League evidence leaves
relegated clubs described only by stale Championship history. That is what the
model does, and the discarded evidence turns out to be worth less than the
boundary regression needed to use it. The division-level part of the signal —
"this club was just in the Premier League" — is well determined and is already
carried by the retained state for 25 of the 30 evaluated entries. The
within-Premier-League part is real in attack but too noisily measured at entry to
survive into forecasts.

## Matched experiment

`runs/relegation-entry-v1`, ten Championship seasons 2016/17–2025/26, 30 relegated
club-seasons, 283 opening matches and 4,000 season paths per cell. All three
treatments share the M7 fixed-p=0.2 Championship parent, incumbent state,
dynamics, conditional Poisson score law and fixture schedule; only the relegated
clubs' entry priors differ. Each club contributes its first ten Championship
appearances, and a match between two relegated clubs is counted once.

This runs on the corrected entry-state behavior. Before that correction the
Championship filter reset every returning club to the flat league population
prior at preseason, which would have confounded the comparison: the relegated
clubs' opponents would have been described no better than the relegated clubs.

| Treatment | Entry prior for a relegated club |
| --- | --- |
| `retained` | Its last Championship state, decayed by the elapsed years; the league population prior when it has none |
| `generic` | The relegation bridge evaluated at the cohort-mean Premier League season, so every relegated club in a season shares one prior |
| `mapped` | The relegation bridge evaluated at the club's own opponent-adjusted Premier League season |

`RelegationBridge` is the existing promotion bridge with its two seasons
exchanged. Source strengths are division-relative Premier League season summaries,
not a filtered end-of-season latent state, because a filtered state would need a
common cross-division scale — the joint hierarchy M9 already tested and failed.
Targets are exposure-adjusted first-ten-Championship-match attack and defence.
Coefficients come only from cohorts whose target season finished before the
evaluated season, growing from 15 training clubs to 42.

## The learned translation

Fitted on all 42 earlier cohorts, for the 2025/26 entry:

| Dimension | Intercept | Slope | Residual SD |
| --- | --- | --- | --- |
| Attack | +0.231 (SD 0.075) | +0.202 (SD 0.198) | 0.082 |
| Defence | +0.228 (SD 0.118) | +0.559 (SD 0.368) | 0.162 |

Coordinates are log-rate attack and defensive strength relative to the division.
The intercepts say a relegated club enters roughly 0.23 log rate above the
Championship average in both dimensions, and the attack intercept is 3.1 standard
errors from zero. The slopes are 1.0 and 1.5 standard errors from zero. Almost all
of the estimated signal is the division-level shift.

This mirrors the promotion direction, where attack has the identifiable slope and
defence does not. Going down, the identifiable slope is in defence. In neither
direction is the boundary a translation of club strength: unit slope is 4.0
standard errors away in attack here, and the promotion bridge rejects it too.

Raw correlations across the 30 entries, ignoring measurement error, are +0.413
(SE 0.16) between Premier League season attack and realized Championship entry
attack, and +0.080 (SE 0.19) in defence. Attack carries genuine within-division
information. The entry label's own noise SD averages 0.260 against a realized
spread of 0.254, so the errors-in-variables fit shrinks that correlation to the
+0.202 slope above, and `mapped` priors span only −0.013 to +0.201 against
realized values spanning −0.347 to +0.657.

## Entry-strength accuracy

Prior against realized first-ten-match entry strength, 30 clubs per cell:

| Treatment | Dimension | Prior SD | RMSE | Bias | Gaussian log score |
| --- | --- | ---: | ---: | ---: | ---: |
| `retained` | attack | 0.160 | 0.251 | −0.011 | 0.064 |
| `generic` | attack | 0.120 | 0.252 | −0.018 | 0.096 |
| `mapped` | attack | 0.122 | 0.244 | −0.031 | 0.065 |
| `retained` | defence | 0.113 | 0.373 | −0.159 | 0.357 |
| `generic` | defence | 0.121 | 0.354 | −0.112 | 0.321 |
| `mapped` | defence | 0.122 | 0.363 | −0.122 | 0.343 |

The three treatments are indistinguishable. Season-clustered differences in
squared error and log score all span zero. `mapped` orders the clubs best —
its correlation with realized entry attack is +0.255 against `retained`'s +0.149
— but it is no more accurate, because ordering 30 clubs inside a 0.21-wide band
does not reduce error against a 1.00-wide realized spread.

All three underestimate defensive strength at entry, `retained` most at −0.159.

## Forecast performance

Season-clustered 95% intervals on paired differences; positive is worse than the
comparator. Full rows in [comparisons.json](relegation_entry/comparisons.json).

| Scope | Comparison | Metric | Difference | 95% interval |
| --- | --- | --- | ---: | --- |
| First five appearances | `generic` − `retained` | score NLL | +0.0243 | [+0.0025, +0.0476] |
| First five appearances | `generic` − `retained` | H/D/A log loss | +0.0111 | [−0.0015, +0.0240] |
| First five appearances | `mapped` − `retained` | score NLL | +0.0182 | [−0.0147, +0.0555] |
| First ten appearances | `generic` − `retained` | H/D/A log loss | +0.0126 | [−0.0005, +0.0260] |
| First ten appearances | `mapped` − `retained` | H/D/A log loss | +0.0086 | [−0.0093, +0.0249] |
| First ten appearances | `mapped` − `generic` | H/D/A log loss | −0.0040 | [−0.0120, +0.0044] |
| Relegated club-seasons | `mapped` − `retained` | rank RPS | −0.0055 | [−0.0455, +0.0346] |
| Relegated club-seasons | `mapped` − `retained` | points CRPS | −0.214 | [−2.475, +2.131] |
| Relegated club-seasons | `generic` − `retained` | 90% points coverage | −0.133 | [−0.267, +0.000] |
| Relegated club-seasons | `generic` − `retained` | 90% points width | −6.53 | [−11.17, −2.47] |
| Relegated club-seasons | `mapped` − `retained` | 90% points width | −6.27 | [−10.80, −2.30] |

Every bridge-versus-retained forecast difference is zero or worse. The only
interval excluding zero on a proper score is `generic` losing 0.024 nats of score
NLL over the first five appearances. Both bridges cut the relegated clubs' 90%
points interval by about 6.4 points and `generic` loses 13 percentage points of
coverage doing it: the bridge prior's SD near 0.12 is tighter than the decayed
state's 0.16 in attack, and that confidence is not earned.

`mapped` − `generic` is within noise on every metric at every scope. Finer
within-Premier-League differentiation buys nothing over "was just in the
Premier League".

## Limits

Thirty entries over ten seasons is a small cohort, and the intervals are wide
enough that a modest real improvement could hide inside them. The first-ten-match
entry label is noisy by construction and cannot be sharpened without using more of
the target season, which would leak. The comparison holds the score law, dynamics
and match-information set fixed, so it does not test whether a different
observation model would make Premier League evidence more transferable. Championship
xG does not exist in this archive, so the source summary is goals only on both
sides of the boundary. The same machinery would apply to League One entrants, but
that division is not in the canonical archive and was not evaluated.
