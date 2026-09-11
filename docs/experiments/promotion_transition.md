# Promotion-transition prior comparison

## Decision

Do not replace the operational entry prior with the process bridge. Championship
shots/SOT do not earn additional permanent prior complexity in this experiment.
Results-only initialization has a small points-CRPS advantage over the pooled
population comparator, but its season-cluster interval spans zero. Retain the
reusable probabilistic transition and its ablations as research infrastructure.

The operational entry treatment was later replaced by the [generic entry
rule](entry_prior.md), which reaches promoted clubs through the same
transition mechanism as every other boundary crosser. The process-signal
conclusion below is unchanged.

## Matched experiment

`runs/promotion-transition-v1` ran from clean commit `7f7e10c`, with the pinned
initial research-ready manifest, ten PL seasons 2016/17–2025/26 and 2,000 paths
per variant. All 30 promoted club-seasons and 144 unique opening fixtures are
matched. Each club contributes its first five fixtures; promoted-versus-promoted
fixtures are counted once. Forecasts are made at preseason, not refitted before
each opening match.

All four variants share the M7 fixed-p=0.2 parent, incumbent/global state,
dynamics, conditional Poisson score law and target schedule. The original
`coarse` entry treatment is itself M7's existing promoted-population bridge,
not a zero-information prior. The new `population` comparator is an intercept-only
transition with the same recent target cohorts as the results/process variants.
It ignores each target club's Championship source strength.

Results uses Championship season goals; process adds shots/SOT. All use identical
complete cases and home/division-adjusted season aggregates. These are noisy
season summaries, not a filtered end-of-season latent state or synthetic xG.
Both dimensions propagate the full within-dimension sampling covariance among
the three summaries. Coefficients are strongly pooled; residual transition
variance is integrated under a half-normal SD prior. Forecast variance includes
source measurement, coefficient and residual-transition uncertainty.

Training labels are exposure-adjusted first-ten-PL-match attack/defense estimates.
Their opponent adjustment uses completed target-season information, so each
cohort is eligible only after that earlier season finishes. There are six
training clubs for the first evaluated season, growing to 33 for the last.
No evaluated season's label enters its own prior. Actual archived retrieval
times remain distinct from the next-day research availability assumption.

## Learned translation

Across the 30 evaluated entries, mean prior attack/defense values are:

| Prior | PL attack mean | PL defense mean | Attack transition variance | Defense transition variance |
| --- | ---: | ---: | ---: | ---: |
| Population | −0.238 | −0.246 | 0.0142 | 0.0296 |
| Results | −0.236 | −0.244 | 0.0140 | 0.0290 |
| Results + process | −0.230 | −0.244 | 0.0138 | 0.0285 |

Coordinates are log-rate attack and defensive strength: negative defense means
more goals conceded. Results-only priors translate source Championship goals
summaries downward by 0.498 attack and 0.607 defense on average. The corresponding
process values are 0.491 and 0.606. These differences combine league translation
and regression toward the promoted population; they are not causal effects of
promotion or a universal fixed division offset.

Total entry variances are larger than residual transition variance: results
0.0267/0.0444 and process 0.0309/0.0494 for attack/defense. Adding weakly identified
process coefficients increases uncertainty even though fitted residual variance
is slightly smaller. Per-cutoff coefficients, SDs and transition-SD intervals
are retained in `priors.json`.

## Preseason promoted-club forecast results

| Prior | Points CRPS | 90% coverage | 90% width | Relegation Brier |
| --- | ---: | ---: | ---: | ---: |
| Existing coarse | 7.827 | 86.7% | 33.73 | 0.2635 |
| New population | 7.821 | 86.7% | 34.47 | 0.2637 |
| Results | 7.732 | 90.0% | 36.00 | 0.2651 |
| Results + process | 7.840 | 86.7% | 36.97 | 0.2710 |

Differences below are candidate minus comparator, with whole-season bootstrap
95% intervals. Lower losses are better.

- Results minus population points CRPS: −0.089 [−0.355, +0.164].
- Process minus results points CRPS: +0.108 [−0.208, +0.398].
- Process minus population points CRPS: +0.019 [−0.450, +0.408].
- Process minus results relegation Brier: +0.00590 [−0.00955, +0.02117].
- Process minus results TRPS: +0.00328 [−0.00262, +0.00874].

Process widens the results interval by 0.97 points [0.53, 1.37] without a
resolved proper-score gain. Thirty promoted club-seasons cannot establish
precise relegation calibration. Nominal coverage attained by one comparator
is not evidence that its full distribution is calibrated.

## Opening fixtures

Results minus population outcome log loss is −0.00030
[−0.00553, +0.00436]; exact-score NLL is +0.00362
[−0.00449, +0.01253]. Process minus results is +0.00453
[−0.00046, +0.00983] for outcome loss and +0.00714
[−0.00411, +0.02013] for exact NLL. Neither elaboration earns its complexity.
The new population comparator is slightly worse than existing coarse on exact
NLL, +0.00765 [+0.00150, +0.01484]. Leave the operational treatment unchanged.

## Limits and retained evidence

This is a bounded initialization test, not a general rejection of process data.
Aggregate source features may miss late-season form. The noisy opening-state
labels use retrospective full-season opponent adjustments. Between-attack/defense
transition covariance is not estimated, and simulation does not share bridge
parameter draws across promoted clubs. Approximate errors-in-variables fitting
and a small promoted population limit precision. No roster-turnover or individual
player effect enters this comparison.

The manifest hash is
`79b9ee1133d78143910f0c6d8448160c7d2d4387f919820189804d43be5c3f3a`;
comparisons hash
`e6ef23c26cdab14faeb2adce7b73f5fe1798c20afa27130fbb87a954c845bb3b`;
completion hash
`eee6caba0eb042d39dbed5efb034c062d470cbfc7de8014dae80d25a1d13b02b`.
The completion record hashes all scored inputs, learned priors and outputs.
The runner and seven focused tests are committed; all 220 project tests pass.
