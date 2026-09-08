# Information and uncertainty batch

Accepted September 8, 2026 from the next-batch steering memo. M2 remains the
operational match benchmark; M7 remains the structural research parent; M8-v1
stays parked. No M9 or broad new model family is in scope.

## Completion requirements

- Championship mechanics: verify current-season rules, configure league-specific
  ranking and test automatic-promotion, final-playoff and relegation boundaries.
- Freeze `research-ready-v1`: recent player transfer/sidelined histories,
  coverage/identity audit, immutable input hashes, valid seasons/competitions/
  signals per experiment, exclusions and actual retrieval/information timing.
  Older archives remain maintenance, not a prerequisite.
- Matched uncertainty ladder: fixed state, posterior uncertainty, future evolution,
  promoted-prior uncertainty, xG observations and retained alternative score law.
  Match training information and initialization; preserve shared state estimates
  and score laws for uncertainty switches. Evaluate preseason/MW6/MW12/MW19/MW30.
- Retain an empirical uncertainty budget: standings TRPS, points CRPS and interval
  coverage/width, title/top-position/relegation Brier, match log loss and exact-score
  NLL. Use season-cluster uncertainty and match-dependence sensitivity. Compare
  M2 match forecasts with calibrated season uncertainty against M4/M5/M7 season
  simulation, explicitly preserving M2 probabilities in the split-product arm.
- Reusable information-value diagnostics for goals, EPL xG, shots and SOT:
  target latent concept, residual information, persistence, complementarity,
  season/league/team stability, state uncertainty, calibration and available-at
  cutoff. Do not assume independent sensors or admit marginal correlation alone.
- Cross-division prior: Championship ending state to PL opening state, pooled
  transition mean/variance, distinct attack/defense or process translation where
  supported, opening matches and preseason points/relegation calibration. Compare
  results-only, actual process observations and hierarchical promoted-population
  prior. Never synthesize Championship xG.
- Conditional roster experiment: if data readiness permits, test strongly pooled
  turnover effects on state discontinuity/transition variance. Elaborate adaptive
  dynamics only if future evolution earns support in the ladder.
- Player work stays behind the oracle gate: team parent, known XI/exposure,
  forecast XI/minutes. Only resume after team sensor/transition findings; no player
  Tilt or defensive symmetry for completeness. Stop if the oracle does not help.
- Twelve-hour collection remains appropriate for team research. Before any late
  availability claim, add explicit T−24h/T−6h/lineup-time capture and per-forecast
  readiness. Historical reconstruction is not prospective information.
- Markets remain external with aligned horizons; closing prices are an upper
  reference. No structural hyperparameter selection by market agreement.
- Automatic retained-run provenance: commit/dirty state, lockfile, invoked script/
  command, Python and relevant dependencies. Establish public-reuse intent before
  choosing a code license; keep provider-data rights separate.

The final report must answer which mechanisms improve early season forecasts,
what independent information process sensors provide, how promotion and turnover
change priors, and which capabilities merit permanent support or retirement.
Passing implementation tests alone does not complete the batch.

## Championship checkpoint

Ranking now follows the football-result criteria in EFL regulations 9.1–9.3:
overall points/GD/goals, head-to-head points/GD/goals, wins, then away goals.
Head-to-head applies to all tied groups, unlike the PL decisive-tie rule.
League configuration controls automatic-promotion and playoff boundaries.
Disciplinary criteria can be supplied to ranking; simulations do not model them,
and explicitly label equal rank allocation when football criteria leave a tie.
Unknown disciplinary evidence is not replaced by zero sanctions.

Sources checked September 8, 2026:

- [EFL 2025/26 regulations, section 9](https://images.gc.eflservices.co.uk/6a32d710-5b0b-11f0-ad0f-97502a343283.pdf).
- [EFL playoff-format announcement](https://www.efl.com/news/2026/march/05/efl-statement--sky-bet-championship-play-off-format/).

The accessible full regulation PDF is labeled 2025/26; the current EFL governance
page exposes an empty content area. Confirming a 2026/27 regulation edition remains
open, so current-season rules verification is not yet claimed complete. Existing
2026/27 configuration retains six playoff qualifiers (positions 3–8).

Verification: `scripts/verify.sh`, 201 passing tests, including each requested
boundary, multi-team ties, criteria precedence, PL regressions and slot conservation.

## Execution provenance checkpoint

Shared forecast/evaluation provenance and the season-evaluation runner now record
Git commit and dirty status, lockfile and script hashes, Python executable/version,
interpreter arguments and application arguments, working directory, and installed
dependency versions (including optional research dependencies). The original shell
or `uv` wrapper invocation is not recoverable from Python; interpreter arguments
are retained explicitly without claiming to reconstruct that wrapper. Non-checkout
installations record unknown Git/lock values rather than inventing a clean state.
Standalone older diagnostic runners still need an execution-provenance adoption
audit. Verification: 203 passing tests, including actual temporary Git repositories
with runner and lockfile mutations.

## Frozen-input checkpoint

`scripts/freeze_research.py` publishes an immutable `research-ready-v1` manifest
with exact per-signal fixture eligibility, complete ordered-pair schedule checks,
player history/identity findings and explicit experiment gates. It pins canonical
publication manifests and hashes, retaining actual request timing. The reader
verifies the snapshot and Parquet checksums and can apply strict retrieval cutoffs.
The eligibility window is bounded to 2013/14–2026/27; older retained publications
remain in the pinned evidence for training provenance, not newly approved sensors.

The initial local snapshot is `runs/research-ready-v1-initial/manifest.json`,
snapshot SHA-256 `776fed3ce2fc679e5d801f9002ade86ef09e2c0e188a4589b05ed09bbc5a00fa`.
It admits twelve complete EPL seasons with xG (2014/15–2025/26), and twenty-six
complete competition-seasons for goals and matched complete-case shots/SOT.
The ongoing 2026/27 season is not a completed-season evaluation target.
This is input eligibility, not a claim of validated models or independent sensors.

The recent four-season population has 2,859 identified API players, with 2,563
transfer and 2,562 sidelined histories absent in this initial snapshot. That is
broader than the current-season population of 1,453 players. Roster/player gates
remain closed. The scheduled bounded backfill was confirmed active (PID 5619);
an extra pass correctly skipped its held writer lock. Do not delete the lock or
restart based on elapsed time. Recheck the actual process before attempting a
larger recent-window pass. A later evidence freeze must use a new output path.

The next implementation priority is the matched ladder over frozen team inputs,
followed by the information-value harness and transition application. Keep the
uncompleted requirements above open. Manifest tests cover immutable snapshot
isolation, corruption rejection, retrospective/strict-cutoff separation, incomplete
season rejection and per-signal complete-case eligibility.

## Matched ladder implementation

The research-only ladder now shares one goals-parent population snapshot across
fixed-state, posterior, deterministic mean-reversion, future-innovation,
promoted-state conditional and alternative-score variants. A matched M7 likelihood
arm adds xG with the same fixed dynamics, population priors and Poisson score law.
The promoted switch conditions current promoted coordinates on their posterior
means (including the corresponding covariance reduction elsewhere); it does not
claim to reproduce refitting historical entry priors. The transition-prior
application remains a separate experiment.

The split-product M2 arm uses a Gaussian copula over repeated team attack and
concession factors. Each fixture still has independent Poisson home/away scores
with exactly M2's fitted rates. Only dependence across future matches changes.
The dependence grid is 0, 0.1, 0.25, 0.5, selected by earlier completed seasons'
points CRPS at the same origin; the first evaluated season defaults to zero.
Markets play no role. Retained M4/M5/M7 are separate product benchmarks.

`scripts/evaluate_uncertainty_ladder.py` evaluates the five requested origins,
retains individual forecasts, season and match losses, and chronological selection
evidence. Match losses here are forecasts of the remaining schedule conditional
on each season origin, not daily-refit forecasts. The companion report bootstraps
whole seasons and shows iid-match, calendar-week and season dependence sensitivity.
No season uncertainty interval is reported from a single season.

The 2023/24 smoke run completed all five origins and twelve variants with 200 paths
per cell in `runs/uncertainty-ladder-smoke`. Its report has 280 season comparisons
and 210 match/dependence comparisons; 30 missing entries are the deliberately
omitted rich benchmarks. These are implementation checks, not retained empirical
conclusions. The full run must include M4/M5/M7, multiple seasons and more paths.
Verification: 208 passing tests, including parent forecast equivalence, covariance
conditioning, unchanged fitted states, copula marginals/cross-match dependence,
and season-level bootstrap clustering.

The larger recent-window backfill encountered two different reported end dates
for the same sidelined episode (API player 19558, suspension starting 2018-02-14).
Raw hash `9272a3027558c74fbe679d57abfc8c64b83de0b5c09103fe00428715afcf35ca`
preserves both. Publication correctly refused contradictory availability keys.
Normalize the disputed end date as unknown and retain an explicit audit before
resuming; do not arbitrarily choose either reported date.

The sidelined repair now consolidates only identical episode keys, marks a
disputed end date unknown, and stores all competing values in the publication's
normalization issues. Raw responses remain unchanged. The existing aggregate
coverage audit already exposes those issues. Independent retained EFL rule-page
captures are checksum-verified but excluded from canonical football-table replay.
Verification: 209 passing tests, including deterministic disputed-episode
normalization, distinct-reason preservation and rule-evidence replay.

The full ladder launched from commit `5678a89` into
`runs/uncertainty-ladder-v1`, using the initial frozen manifest, 2015/16–2025/26,
2,000 paths per cell, and all rich benchmarks. It remains in progress; do not use
partial summaries as the batch conclusion. The process handle is exec session
39240. The repaired bounded recent-window backfill is exec session 38720; its
budget is 3,000 requests with the existing daily reserve. Revalidate live handles
and process state before resuming either; do not duplicate running jobs.

## Information-value harness checkpoint

`scripts/evaluate_information_value.py` extracts pre-observation M7-member state
controls for both leagues, then evaluates new goals, EPL xG, shots and SOT against
future own-team scoring at lags one, three and six within-season team matches.
Championship uses M7's goals-only marginal with the same dynamics; no Championship
xG is created. Source retrieval timestamps/hashes stay separate from the explicit
next-day research availability assumption. Known future fixture identities/dates
are retrospective schedule controls, not claimed historical schedule snapshots.

Sensor residualization, pooled ridge coefficients and variance estimates fit only
earlier seasons whose targets have matured before the evaluated information
cutoff. Every sensor subset in a league/horizon uses identical complete cases.
The report includes incremental and leave-one-sensor-out comparisons, whole-season
intervals, season/team stability, residual correlations and within-team residual
persistence. Gaussian proxy scores/intervals apply to noisy future log1p-goals;
they are not match-score NLL or latent-state calibration claims.

Separate identical-prior Laplace updates measure goals and goals+xG effects on
joint latent match log-rate variance. Shots/SOT are not assimilated or assigned
invented posterior precision. A known Gaussian-state/correlated-sensor check
validates dependence accounting, explicitly outside football-model validation.
In its fixed 20,000-draw test, joint-noise 90% coverage is 90.065%; incorrectly
independent noise yields 65.845% coverage.

The final two-season smoke artifact is `runs/information-value-state-smoke`:
2014/15 supplies initial fitting and 2015/16 supplies evaluation, both leagues.
It completed 177 matched residual comparisons and 21 persistence summaries;
single-season uncertainty intervals are left unknown. The earlier
`runs/information-value-smoke` predates the posterior/persistence additions and
is retained only as an implementation checkpoint. All 212 tests pass, including
future-target isolation and redundant-sensor covariance checks. Multi-season
empirical interpretation and the promotion/offseason application remain open.

The full information-value run completed from `4cc1131` in
`runs/information-value-v1`. The [empirical report](experiments/information_value.md)
records the exact evidence hashes and findings. Individual sensor improvements
are not stable under season-cluster uncertainty. Shot residuals persist modestly,
but their complementarity with existing observations is not established. Keep
shots/SOT out of an independent production likelihood; test pooled transition
summaries against the population prior before drawing a promotion-prior decision.

Execution provenance now also covers the older diagnostic runners. Shared run
directory creation writes content-addressed immutable execution records; rerunnable
reports retain separate records for distinct commands/code without overwriting the
previous execution evidence. The season rescoring/reporting and retained M6 audit
paths are included. All 213 tests pass, including preservation of prior execution
records across changed invocations. The public repository has no code license;
an asynchronous user choice about MIT-for-code-only is pending. No provider-data
rights are altered.
