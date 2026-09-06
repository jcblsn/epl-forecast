# M6 squad and player batch

Source: September 6 steering feedback supplied in the attached text. Its linked
longer sandbox memo is not present in this workspace. M2 stays the operational
reference, the promotion prior stays fixed, and existing captures and archives
are retained. Historical periods already inspected are development evidence.

Completion requires all of the following, with retained inputs and results:

- Investigate M5 grid support separately from accumulated Laplace evidence error;
  assess league level jointly with common Tilt, scoring rates and season outcomes.
- Build candidate squads at a cutoff without reading target participants. Record
  identity, club membership, observation times, availability and fallback coverage.
  Distinguish timestamped snapshots from retrospective appearance reconstruction.
- Sample coherent lineups and minutes; audit newcomer, opening-week and transfer
  coverage. Add current player fixture-history capture without altering archives.
- Fit a strongly pooled player Quality layer jointly with club/system strength,
  state the identifying assumptions, and compare a small sampled reference.
  Evaluate a restrained role/composition Tilt extension separately.
- Integrate uncertain future minutes and player effects into scores and season
  paths. Demonstrate an expiring absence/replacement scenario from a recorded
  snapshot, tracing lineup, strength, probabilities, expected points and table.
  Check direct probabilities against simulated frequencies.
- Write one decision report comparing unchanged M2, the selected M5 parent and
  incremental M6 variants on identical fixtures and cutoffs. Retain chronological
  predictions and opening, promoted, lineup-change and newcomer slices. If xG is
  used, include a team-only xG control. Preserve timestamped forward forecasts.

No default switch is justified by implementing Bayesian machinery alone. Broad
baseline tuning, news/manager/market layers, frontend redesign and scheduling
infrastructure remain outside this batch.

## Verified progress and remaining work

- Cutoff-specific squads and coherent lineup sampling are committed. The full
  three-season lineup coverage audit is in `experiments/m6/lineup_coverage.json`.
  Opening-week roster gaps remain explicit; lineup baseline comparison is pending.
- The bounded M5 investigation is complete in `experiments/m6_m5_uncertainty.md`.
  It separates grid support from evidence integration and identifies a common-rate
  posterior-mean bias supported by a sampled reference. Moment correction remains
  a research alternative. Existing Poisson M5 is the primary M6 parent comparison.
- Current player fixture capture and timestamped normalization are implemented.
  The first 653-endpoint capture is recorded in `experiments/m6/current_player_capture.json`.
- Still required: hierarchical club/player inference and its sampled reference;
  separate Quality and role/Tilt variants; lineup and player uncertainty through
  match and season forecasts; an expiring absence scenario; direct/simulated match
  agreement; identical-cutoff model comparisons with promoted/opening/change/newcomer
  slices; and the final comparative decision report. No xG has entered modeling.
