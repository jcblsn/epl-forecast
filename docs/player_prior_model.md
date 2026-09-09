# API-FOOTBALL time-local player prior

This retained research candidate adds a learned time-local prior to the existing scalar
player Quality diagnostic. It has a separate evaluation path and is not wired
into operational forecasts or season simulations.

Its centered match-likelihood design is superseded for player-information
discovery by the standalone layer and the
[architecture work plan](architecture_next_phase.md). The specification below
records V1, including its original provider-field interpretation. The subsequent
[player prechecks](experiments/player_layer_prechecks.md) establish null-as-zero
semantics for the relevant event fields and identify `pass_accuracy` as a
completed-pass count. Those findings invalidate an unconditional-rate reading of
V1's non-null-only denominators; they are not silently applied to its old results.

For player i before London date t, the approximation is

`beta(i,t) = X(i,t) theta(role) + u(i) + epsilon(i,t)`.

The player residual u is persistent, initially Normal(0, 0.35²). The role-specific
mapping has a shared Normal(0, 0.12²) coefficient plus a Normal(0, 0.08²) role
deviation for each feature. The implementation integrates the shared coefficient
analytically into the covariance between role coefficients. The mapping and
residuals are fitted jointly with club states using the existing chronological
daily Poisson/Laplace likelihood. Club/mapping/player cross-covariances persist.

The local error epsilon is zero-mean Gaussian with variance
`0.15² + 0.45² * 900 / (900 + relevant_effective_minutes)`. It is marginalized
within each day's match update; it does not create an evolving player trajectory.
This fixed regularization law contracts with relevant exposure and widens as
exposure decays. It is a modeling assumption to diagnose, not a claim of calibrated
measurement uncertainty. Reported prior moments integrate mapping uncertainty,
persistent residual uncertainty, their covariance and local uncertainty.

## Features and pooling

Five counts enter V1: total passes, shots, key passes, duels won, and goalkeeper
saves. Recent and long-run half-lives are 45 and 240 days. Every rate is shrunk
toward its role/competition/season population using 900 pseudo-minutes before
standardization. Population moments borrow 9,000 pseudo-minutes successively
through role, role/competition, and role/competition/season levels. Only earlier
eligible appearances enter any level. The hierarchy starts with mean zero and
unit second moment when there is no observed population evidence.

The resulting standardized rate features are bounded to ±3. Additional features
are a pooled role intercept, log effective minutes, capped days since a prior
30-minute appearance, relevant-statistic coverage, age, and the level of the
player's last observed competition. The model learns all feature weights through
match scores. Unknown roles average the four role designs; unseen players receive
pooled intercept/competition means and population residual uncertainty. Known
player features follow stable API identity across transfers. Club reference
exposure remains with the club.

There are 16 inputs per role, 64 mapping coefficients in total. The explicit
rating ablation adds recent/long-run minute-weighted ratings, producing 72
coefficients. Rating never enters the primary candidate. Count denominators
include only minutes where the field is observed. Null remains missing. Several
event fields have substantial missingness, so these are conditional observed
rates, not proven unconditional rates. The retained coverage audit makes that
limitation inspectable. Saves exposure is relevant for GK; passing, shooting,
creation and duels exposure are relevant for other roles.

Pass accuracy is retained verbatim as a canonical string. The 2022–2024 payloads
contain bare values above 100 and no percent suffixes; its units are not assumed
and the field is excluded from V1. Eight contradictory key-pass/total-pass pairs
are marked unknown, with raw values and source hashes preserved in the audit.
The provider's [fixture-player description](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
identifies the available field families and the proprietary rating.

## Centering and chronology

Each club's reference is its last five observed match minute shares, weighted
with the 45-day half-life. Every training and forecast player term uses lineup
share minus reference share. Identical lineups cancel the entire layer, including
its uncertainty. A club without prior reference exposure receives no player
adjustment. Historical actual minutes are used in training; future minutes are
sampled with the existing prior-appearance/carry-forward lineup machinery.

Same-London-date results are always excluded. Retrospective captures become
eligible by fixture chronology; captured observations also respect their capture
date. Birthday profiles must be labeled to an already completed prior season.
They provide fixed biological metadata, with age calculated at the cutoff;
contradictory birthdays remain unknown. Historical publication timing is not
established by these backfills. Current squads, transfer histories and injury
histories are not backdated into this experiment. Opening squads use the existing
0.7 carry-forward membership assumption and do not discover future arrivals.

Oracle distributions use actual target identities/minutes with exactly the same
fitted prior. Target statistics and target roles never enter the prior, even in
the oracle. Outcome-based slice labels are computed separately after forecasting.

## Evaluation contract

Freeze 2022/23 through 2024/25 API-only fixtures and player profiles. Use 2022/23
as feature history, expanding match-likelihood training from July 2023, and all
380 2024/25 PL fixtures as targets. All regimes retain the original four M5
independent-Poisson dynamics specifications and 32 lineup draws per specification.
Hyperparameters above are fixed before scoring; no leaderboard tuning is used.

Retain team parent, existing M6, a centered control with feature mapping disabled,
the new prior, and its rating ablation. Every player model is scored under both
forecast minutes and explicitly nondeployable oracle minutes. The centered control
shares the new prior's residual and local-error law, so its paired comparison
isolates the learned mean. M6 remains a separate historical zero-centered-prior
comparison. Report outcome log loss, score NLL, Brier score, fixed-bin calibration,
paired day-bootstrap intervals, all requested slices, individual-prior movement,
and probability movement. This is bounded research evidence, not promotion.
