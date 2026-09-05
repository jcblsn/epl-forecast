# Implementation plan

Build a current Premier League forecasting product and improve its predictive
information. The historical data, model interface, chronological harness and
season simulator are established. Their initial evidence remains in
[E001](experiments/E001.md) and [E002](experiments/E002.md).

## Current work

As of 2026-09-05:

1. Archive live sources: implemented with `data snapshot`. Five public responses
   have been captured, with raw bytes and observation times.
2. Generate the current 2026/27 forecast: implemented with `forecast`. Export
   strengths, match probabilities, score matrices and season distributions as
   JSON/CSV/HTML. Preserve every forecast and distinguish its model cutoff from
   the actual capture and archival timestamps.
3. Tune M2: completed the 30-setting rolling search with selection from earlier
   seasons. Defaults already sit in the best region; [retain them](experiments/m2_tuning.md).
4. Use Championship history for promotion continuity, then test lagged shots,
   scoring distributions and dynamic team-strength uncertainty.

The detailed order is in the [research queue](next_experiments.md). Live capture
continues while model work proceeds. No background scheduler is installed yet.

## Contracts worth keeping

- Canonical team IDs and stable ordered fixture IDs, even after rescheduling.
- Raw retention and basic provenance; explicit source failures and score conflicts.
- Prior-date results for fitting, with no same-day leakage. Captured full-time
  results may be fixed in the live table without entering that day's fitted model.
- Valid probabilities, complete score PMFs or disclosed display tails, and
  unbounded score sampling.
- All 380 ordered fixtures, fixed played scores, points/goal conservation and
  honest European qualification assumptions.
- Archived forecasts are forward evidence only when completed before kickoff.
  Replaying an old snapshot cannot manufacture a historical pre-match archive.

## Verification effort

Run Ruff and relevant tests for changes. Keep leakage, probability, identity,
cutoff and simulation arithmetic tests. Check deterministic normalization when
its implementation changes; use full fresh-directory reproduction occasionally
or for releases. Reserve expensive statistical analysis for comparisons that
warrant it. Most negative exploratory ideas need a short note and a table.
