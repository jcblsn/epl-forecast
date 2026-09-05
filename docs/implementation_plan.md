# Implementation plan

The first deliverable is the six-part milestone in `design_preliminary.md`, with
working commands and saved evidence. Later phases remain experiments, not promises
that complex models will improve predictions.

Status on 2026-09-05: the first milestone is implemented and reproduced from a
fresh data directory. [E001](experiments/E001.md) records the results, comparison
decision and verification evidence. Phase 0 and the initial evaluation harness
are complete. [E002](experiments/E002.md) adds and evaluates an Elo/ordered-logit
benchmark; it does not meet the gate for replacing M2. Both experiments are
checkpointed in Git, and completed future milestones should be committed at
similar intervals. Dynamic models,
distribution experiments and richer information layers remain in the
[research queue](next_experiments.md).

1. Finish the data audit. Acquire immutable raw CSVs, pin URLs/checksums/retrieval
   times, normalize canonical identities, and generate field and schedule audits.
2. Establish the forecasting contract. Training receives completed matches before
   the forecast date; prediction receives only fixture information. Enforce the
   same daily information cutoff for every model.
3. Build rolling-origin evaluation, per-match predictions, log loss, multiclass
   Brier score (sum across three classes), classwise calibration, and score log
   likelihood where available. Report market benchmarks on explicitly matched rows.
4. Compare trivial and team-level benchmarks after inspecting the full audit.
   Freeze model/config versions, retain per-season results and paired uncertainty,
   and distinguish development comparison from a final untouched season.
5. Simulate a historical PL remainder from a fixed cutoff, redacting future results.
   Verify schedule completeness, standings arithmetic, tie handling, reproducible
   random draws, points/goal-difference distributions and probability sums.
6. Publish reproducible commands, experiment results and limitations. Add a tested
   next-experiment queue based on the observed data and errors.

## Decisions to settle explicitly

- Missing kickoff times: use daily batches and next-day result availability.
- Identity: reviewed source aliases; match IDs use competition, season and ordered
  opponents, remaining stable if a fixture is postponed.
- Sources: public Football-Data CSVs currently support this milestone without keys.
  Optional authenticated sources must be probed before they become dependencies.
- Reproducibility: a lockfile pins each raw blob; processing and evaluation work
  offline. Restoring a changed upstream blob fails instead of silently changing data.
- Modeling: simple Python modules, NumPy/SciPy as needed, a small CLI, no frontend.
- Simulation: a score model must provide unbounded sampling and observed-score
  likelihood; any display grid truncation must expose its omitted mass.
- European places: top-four/top-five probabilities alone are not qualification
  forecasts. Support explicit season/scenario assumptions about cup winners and
  European performance slots, and label conditional outputs.
- Ties: use PL points, goal difference and goals scored; head-to-head rules apply
  when deciding title, relegation or qualification. Exact unresolved ties need
  explicit treatment, not alphabetical sorting.
- Historical rules and deductions: keep them separate from forecast fitting. Do
  not insert a later sanction into an earlier simulated table.

## Verification gates

Data: determinism, raw corruption detection, season counts, malformed scores,
unknown aliases, duplicate fixture rejection, and explicit missing optional fields.

Forecasting: future-score mutation invariance, same-day isolation, cold starts,
probability normalization, analytical score likelihood, and identical seeds/configs.

Simulation: played matches stay fixed; each remaining ordered pair is sampled once;
points and goals balance; head-to-head and tied positions are handled; final
probabilities conserve title and relegation slots; deductions obey their known date.

Acceptance: a fresh data directory can restore the pinned data; two offline
normalizations agree byte-for-byte; a chronological comparison of at least two
simple models runs; an actual PL season simulation completes; tests and Ruff pass.
