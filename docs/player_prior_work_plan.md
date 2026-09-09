# API-FOOTBALL time-varying player prior

The September 9 steering memo requests a bounded research candidate and matched
chronological evidence. This is a separate information layer; the operational
benchmark is unchanged. Completion requires all of the following.

1. Extend canonical API-FOOTBALL appearances from retained fixture payloads,
   preserve missing values and raw evidence, and audit historical coverage and
   ambiguous fields. Keep other providers, predictions and odds outside the input
   manifest. Support old canonical partitions without losing the new columns.
2. Build deterministic, cutoff-safe recent/long-run player features, exposure and
   staleness uncertainty, role/competition pooling, and age where defensible.
   Player identity persists across transfers. New players use pooled priors.
3. Fit a small, regularized role-specific mapping against the chronological match
   likelihood with persistent shrunk player residuals and joint club covariance.
   Center actual/forecast personnel against a prior recent reference squad.
   Expose scalar prior moments through an extensible component interface.
4. Compare team parent, existing player model, centered zero-mean control, new
   prior, and actual-minutes oracle on identical chronological fixtures. Include
   a rating ablation, calibration, paired scores, requested slices, and player
   and probability movements. Freeze inputs, configuration and commands.
5. Add meaningful synthetic tests for chronology (including same London date),
   time variation, shrinkage, transfers, missing statistics, unseen players,
   reproduction and target-stat/minute isolation. Run `scripts/verify.sh`.
6. Retain the evidence and explain what it says about the prior representation
   versus lineup information. Audit every requirement before claiming completion.

The intended first evaluation uses 2023/24 for match-likelihood warmup and all
2024/25 PL fixtures for scoring, with earlier API-FOOTBALL appearances supplying
feature history and Championship observations supplying promotion/competition
context. Hyperparameters are fixed before scoring. No performance claim follows
from the leaderboard or from an implementation test.

## Progress

- Read the memo and inspected M6, the canonical capture architecture and retained
  API fixture payloads. The raw data already contain the richer statistics.
- Implementing schema compatibility and deterministic replay into an isolated
  research dataset. Passing accuracy will remain the provider's raw string:
  bare numbers have ambiguous units and will be audited and excluded from V1.

## Superseded for discovery

The [standalone player-process layer](experiments/player_layer.md) supersedes this
plan as the mechanism for discovering how much portable information belongs to a
player. Club centring is unchanged and still solves the downstream double-counting
problem; it is simply no longer where player information is learned, because an
ever-present player produces almost no lineup-share variation for it to learn from.
The V1 prior, its evaluation contract and its retained evidence stand as they are.

Two findings from that batch bear on V1 directly. API-FOOTBALL writes a null for zero
on `goals`, `shots`, `shots_on_target`, `key_passes` and `saves`, so V1's treatment of
those nulls as missing computes each rate over only the exposure in which the event
occurred, inflating every player and compressing the differences between them. And
the retained `pass_accuracy` string is a completed-pass count, not a percentage: it
never exceeds `passes_total` across 164,106 paired appearances, correlates with it at
0.980, and exceeds 100 only where the total does. Excluding it was correct under the
earlier evidence; the unit is now resolved.
