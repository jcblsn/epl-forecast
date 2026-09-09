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
