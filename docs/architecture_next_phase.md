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

Gate 3 is in progress. `research/roster_bridge.py` and
`scripts/evaluate_roster_bridge.py` implement an attacking-only known-minutes
bridge on the exact saved M2 and M7 forecast distributions, with baseline states
held fixed. The mapping fits exactly two coefficients, no intercept, and ridge 1
using a chronological Poisson mean estimating equation. Actual target minutes
are compared with the previous eight eligible team matches, requiring at least
three reference matches. Scoring begins on 2024-08-01 after at least 200 training
fixtures.

This first bridge uses expected portable traits as plug-in inputs. It exports a
trait-variance audit but does not integrate that uncertainty into forecasts.
Whole-population and transfer, injury, large-lineup-change (at least two player
match equivalents), opening (first five matches) and promoted slices are required
in the retained report. Reconstruction covered all 1,140 saved baseline matches;
M7 likelihood agreement was within 8.9e-16. Five synthetic bridge tests pass.
The empirical run `runs/roster-bridge-v1` is preparing; no empirical bridge result
or dynamic-state result is claimed here. The full objective remains open.

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
- [Portable-player interface](portable_player_interface.md): trait distribution,
  chronology, provenance and downstream consumption contract.
- [Original player report](experiments/player_layer.md) and
  [prechecks](experiments/player_layer_prechecks.md): historical experiments;
  superseded claims are identified by the corrected evidence.
- [Data migration](data_architecture_migration.md): remaining ingestion/archive work.
- [Live operations](live.md) and [season evaluation](season_evaluation.md): capture,
  point-in-time provenance, simulation outputs and product-level scoring.
