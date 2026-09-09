# Joint forecasting architecture: next phase

This work follows the steering memo supplied on 2026-09-09, starting from
`1999ec0`. M2 remains the operational benchmark and M7 the retained xG benchmark.
Neither fixes the final architecture. Historical player-layer conclusions in
`experiments/player_layer.md` must be read against the corrected experiments below.

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

## Current checkpoint

The first corrections are implemented; corrected retained-data evaluations and the
full repository verification are in progress. No bridge or dynamic-state result is
claimed yet. The full objective remains open.

The depth-matched API control uses all API appearances starting at the earliest
eligible retained process observation at each cutoff, including role-population
estimates. It matches calendar depth, not individual provider linkage; unresolved
process identities therefore remain a measured difference in information coverage.
API-only means API player predictors and API evidence-depth uncertainty; Understat
is still the supervised target and supplies the shared target-role rate offset.
