# Joint forecasting architecture: next phase

This work follows the steering memo supplied on 2026-09-09, starting from
`1999ec0`. M2 remains the operational benchmark and M7 the retained xG benchmark.
Neither fixes the final architecture. The
[corrected player evidence](experiments/player_layer_corrections.md) supersedes
the original horizon, reliability and API-control claims.

## Evidence sequence and completion requirements

1. Correct the standalone player controls: explicit 90/180/240-day transfer
   horizons; provider-null-as-zero reliability; API-only features and uncertainty;
   an API comparison restricted to the process-history calendar window. Retain
   matched scores, source provenance, and a revised portability decision.
2. Freeze a cutoff-safe distribution over shooting/chance generation and creation,
   including exposure, staleness, uncertainty and provenance. Preserve dimensions;
   the rejected xG+xA aggregation does not reject every downstream scalar.
3. Fit a chronological, attacking-only known-minutes roster-delta mapping on saved
   M2 and M7 rates. Reference recent personnel at application time; hold baseline
   states fixed. Report whole-population and transfer, injury, large-lineup-change,
   opening and promoted slices. Diagnose a one-baseline-only improvement or a
   structurally inadequate mapping before choosing further complexity.
4. Implement one bounded dynamic-state candidate: common PL/Championship hierarchy,
   persistent two-dimensional club states across divisions, league level, changing
   home advantage, explicit uncertainty and sequential Bayesian updates. Check
   goals-only mechanics first, then noisy team-xG observations. Treat attack/defence
   and Quality/Tilt as coordinate choices. Keep M2 and M7 in matched comparisons.
5. Keep independent Poisson as control and test exactly one shared Gamma match-
   intensity score law for dependence and overdispersion. Judge score likelihood,
   H/D/A forecasts and season tails before adding any complexity.
6. Conditional on bridge evidence, integrate forecast minutes and audit inexpensive
   foreign-arrival priors. Player deltas remain centred against personnel represented
   by the team state and affect attack only.
7. Simulate PL and Championship jointly with current-state draws, future state
   innovations, future personnel and scores. Reuse verified exact competition rules;
   report points and every position, title/Europe/relegation, automatic promotion,
   playoffs and promotion. Do not filter states on randomly simulated scores.
   Validate season calibration and Monte Carlo precision, including parameter risk.
8. Once the structural core is stable, compare a chronological de-vigged market
   measurement or calibrated pool. Retain a separately measurable structural arm.
   Archive forecasts and explain material changes from the coherent state.

## Bridge and state contracts

For the known-minutes diagnostic, save pre-match M2 and M7 rates before applying
any player adjustment. Fit the smallest chronological mapping B in

```text
log(rate*) = log(rate_base) + B [P(actual target minutes) - P(recent reference roster)]
```

P retains at least shooting/chance-generation and creation dimensions from the
frozen player layer. Traits, uncertainty and reference exposure use only evidence
eligible at the cutoff. Actual target identities/minutes are an explicitly
nondeployable oracle input; target process statistics never become predictors.
Player deltas affect own-team attack only. Keep baseline states fixed and use
no player defence, player Tilt or lineup forecasting in this test.

The bounded state candidate keeps each club's latent two-dimensional scoring state
as it crosses divisions. Hierarchical league-level terms and observed transitions
identify a common scale. Goals-only observations establish the state mechanics;
team xG is then a noisy process measurement, with no independent double-counting
of goals or forced equality to additive player xG. Home advantage may vary slowly.
An attack/defence-to-Quality/Tilt rotation does not create a second model family.

For season paths, draw current latent states, future innovations, personnel and
scores in that order. Random simulated scorelines do not filter an already drawn
latent path. Conditioning on a user's hypothetical observed result is a separate
filtering calculation. Record path counts and Monte Carlo uncertainty for tails;
no particular simulation count substitutes for precision evidence.

## Current checkpoint

The player correctness gate is complete. The
[corrected 90/180/240-day evaluations](experiments/player_layer_corrections.md)
use fully elapsed target windows and retain 61, 76 and 70 transfer episodes,
respectively. Shooting remains portable across all three horizons. Creation has
weaker support, with the 240-day transfer interval including zero. API creation
gains on chronological targets do not establish transfer gains; matching calendar
depth performs worse on longer-horizon transfers. These findings support freezing
the small trait vector without reopening general feature tuning.

The [portable-player interface](portable_player_interface.md) is implemented and
verified: the full repository check passes 278 tests, and a
[retained sample export](experiments/player_layer_corrections/portable_example.json)
records its distribution and provenance. Gate 2 is complete. The interface
preserves separate long-run shooting and creation sufficient statistics and
exposure/staleness uncertainty. Its Gamma latent-rate uncertainty is explicitly
uncalibrated; the standalone future-process interval scores do not establish this
interface's coverage.

Gate 3 is complete and negative. The
[known-minutes roster bridge](experiments/roster_bridge.md) improves neither
baseline: across 760 chronological fixtures the paired outcome-loss difference is
+0.00178 against M2 and +0.00108 against M7, and every whole-population and slice
interval includes zero. The plan's diagnosis requirement resolves to a
structurally inadequate mapping rather than a one-baseline-only improvement.

The [representation check](experiments/roster_bridge/representation_audit.json)
rules out estimation as the cause. Refitting the two coefficients in sample on
the evaluation window itself, the entire attainable Poisson log-likelihood gain
is 0.42 nats for M2 and 0.01 for M7 over 1,520 team-matches, both coefficients
sit under one standard error from zero, and a permutation null is not rejected.
The design is well conditioned throughout, so no coefficient choice for this
contrast could have helped. Averaging the reference over eight matches diffuses it
across so many players that ordinary rotation registers as a large personnel
change: 87.4% of team-matches already exceed the plan's two-equivalent threshold,
which is why the required large-lineup-change and injury slices cover 97.4% and
94.5% of fixtures and separate no distinct population. A positive shooting
coefficient appears only in the 5.4% of team-matches with the largest personnel
change; that stratum is in-sample on a post hoc threshold and is a direction, not
evidence.

This is negative evidence about the tested contrast, not about the player-
information hypothesis. The channel is parked with one bounded second formulation
available under the research principles: an identity-preserving normal-XI or
core-roster reference on a genuinely discontinuous population. That work waits on
the cross-division club-state results, which define what the club state is already
meant to have absorbed. The frozen portable interface is unaffected, and Gate 6
stays closed until such a contrast produces evidence.

Gate 4 is complete and negative on forecasts. The
[cross-division club-state candidate](experiments/cross_division.md) keeps one
Quality/Tilt state per club across both divisions, adds Championship scoring-level
and home offsets as slow random walks, and reuses the M7 opportunity likelihood
for team xG. Its mechanics hold: planted scoring level and home advantage are
recovered at nominal coverage, crossings rather than the prior identify the common
scale, xG sharpens the state, and the attack/defence rotation reproduces forecasts
to 5.6e-17, confirming a coordinate choice rather than a second model family.

On 760 matched validation fixtures it loses +0.01413 [+0.00890, +0.01943] against
an uncentered bridge control that differs only in resetting promoted clubs, and
+0.00778 [+0.00454, +0.01148] against M7. The loss concentrates on the promoted
slice at +0.05179, roughly four times the whole-population effect, which is the
population the hierarchy was meant to serve. Within M9 team xG still gains
-0.01042 [-0.01856, -0.00210]: the observation channel works, the state structure
does not.

Two diagnostics say why. The retained promotion bridge's realized cohorts give a
Championship-to-Premier-League slope of 0.539 (SD 0.317) in attack and 0.074 (SD
0.250) in defence, against the unit slope a carried state assumes; the transition
is a compression, not a translation. Independently, a synthetic regime with a
planted absolute strength gap and preserved club identity overstates promoted
clubs by +0.0465 (SE 0.0059) in log rate while a zero-gap regime is unbiased, so
an additive-only division level cannot absorb a population difference even when
identity truly persists.

Two properties of the run constrain interpretation. The hierarchy's sensors are
asymmetric: Understat covers 75.1% of Premier League matches and no Championship
match, so promoted clubs always arrive with goals-only states. And in the
uncentered coordinate the Championship scoring level is prior-dependent, moving
1.25 to 1.49 posterior SD across a prior grid, driven almost entirely by the Tilt
innovation scale; it is a working coordinate, not a settled latent quantity. Home
advantage is unaffected, moving 0.0003 across the same grid, and its decline from
about +0.25 in 2017 to about +0.20 in 2026 is retained.

The next state formulation is stated in the report: a division map that compresses
club states toward the division population, with the coordinate settled so league
terms own the corresponding means, judged on the promoted slice and the planted-gap
calibration rather than whole-population loss. Gate 5 is independent of this
outcome.

The depth-matched API control uses all API appearances starting at the earliest
eligible retained process observation at each cutoff, including role-population
estimates. It matches calendar depth, not individual provider linkage; unresolved
process identities therefore remain a measured difference in information coverage.
API-only means API player predictors and API evidence-depth uncertainty; Understat
is still the supervised target and supplies the shared target-role rate offset.

## Documentation and retained evidence

Keep [the north star](north_star.md) limited to product outcomes. This file owns
active architectural decisions, evidence ordering and outstanding requirements;
update its checkpoint as retained results arrive. Model specifications describe
implemented mechanisms and experiment reports own empirical claims. Remove stale
plans when their useful content is retained elsewhere; Git preserves their history.

- [README](../README.md): current commands, product capabilities and limitations.
- [Research principles](research_principles.md): interpretation and comparison rules.
- [Information and uncertainty evidence](uncertainty_work_plan.md): prior batch,
  reusable runners, current-rule evidence and unresolved product limitations.
- [M7 report](experiments/m7_xg_parent.md) and [M8 report](experiments/m8_process.md):
  retained xG benchmark and parked observation candidate.
- [Corrected player evidence](experiments/player_layer_corrections.md): completed
  horizon, reliability and API-control comparisons, with archived per-case scores.
- [Known-minutes roster bridge](experiments/roster_bridge.md): the negative Gate 3
  result and the identification and representation check that closed it.
- [Cross-division club states](experiments/cross_division.md): the Gate 4 state
  candidate, its promoted-slice failure and the scoring-level identification audit.
- [Portable-player interface](portable_player_interface.md): trait distribution,
  chronology, provenance and downstream consumption contract.
- [Original player report](experiments/player_layer.md) and
  [prechecks](experiments/player_layer_prechecks.md): historical experiments;
  superseded claims are identified by the corrected evidence.
- [Data migration](data_architecture_migration.md): remaining ingestion/archive work.
- [Live operations](live.md) and [season evaluation](season_evaluation.md): capture,
  point-in-time provenance, simulation outputs and product-level scoring.
