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

## Promotion-transition implementation checkpoint

The pooled entry-prior comparison now has a dedicated runner,
`scripts/evaluate_promotion_transition.py`. It compares the unchanged coarse M7
entry treatment with a promoted-population prior, a Championship-results prior,
and a results/shots/SOT prior. Incumbent and global-state moments, forecast
dynamics, target fixtures and simulation seeds are matched. Source summaries are
home/division-adjusted season aggregates, not a claimed filtered ending state.
The bridge integrates coefficient and transition uncertainty and carries the
correlated sampling covariance of goals/shots/SOT within attack and defense.
Between-dimension transition covariance and shared bridge-parameter simulation
across clubs remain explicit limitations.

Only earlier completed PL target cohorts enter each prior; full-target-season
opponent adjustment is retrospective label construction, not a target-season
forecast input. The opening-match score is a preseason forecast of each promoted
club's first five matches, not a daily-refitted or lineup-informed forecast.
Results and process comparators share source complete cases. The population
comparator ignores source strength and its measurement covariance.

`runs/promotion-transition-smoke` completed all four variants for 2023/24 with
100 paths. Tests cover cutoff isolation, known-transition recovery, correlated
measurement-noise propagation, population invariance and unchanged incumbent
moments. Full multi-season empirical results are not yet claimed.

The main ladder has finished all eleven seasons and five origins in
`runs/uncertainty-ladder-v1`; its attribution report contains 400 season and 300
match comparisons with no missing pairs. Its empirical write-up is next.

The [uncertainty-budget report](experiments/uncertainty_budget.md) now records
the full empirical result and input hashes. Current-state uncertainty earns
early-season support; innovations do not earn adaptive elaboration. Calibrated
M2 season dependence improves preseason points CRPS and TRPS while preserving
match probabilities exactly. Richer season models do not establish a reliable
preseason advantage over that split product. The gamma score-law change is not
admitted. These are development findings, not a production-model switch.

The promotion runner was committed and pushed at `7f7e10c`, with all 220 tests
passing. `runs/promotion-transition-v1` is running the ten admitted target
seasons 2016/17–2025/26 with 2,000 paths per variant from that clean checkpoint.

That run has now completed all four variants, with 30 promoted club-seasons and
144 unique opening fixtures per variant. The
[promotion-transition report](experiments/promotion_transition.md) records means,
transition variances, forecast calibration and paired uncertainty. Process
statistics widen priors but do not improve opening or preseason proper scores
reliably beyond results/population. No operational prior change is made.

Remaining batch work is the bounded recent-history completion and final identity/
coverage freeze, the conditional roster-discontinuity feasibility/test, the
player oracle gate after team findings, and current EFL-edition verification.
The license choice remains pending. The twelve-hour capture schedule and M2/M7/
M8 roles are unchanged. The backfill session `38720` remains active; do not start
a competing writer merely because it is quiet.

## Explicit player-evidence gate

The readiness manifest now records fixture-level `player_oracle_evidence` IDs,
intersecting team xG and usable starters with linked player-process identities,
matching positive-exposure participants, valid process exposure/observations,
and no same-team identity collision. Multiple process records cannot silently
collapse to one canonical player. Unknown IDs are reported as unlinked, not as
duplicate canonical identities. Provider minute totals remain separate; these
necessary identity checks do not establish a calibrated allocation likelihood
or historical information availability.

The live canonical audit found only 30 current-season player-process fixtures,
929 records and 309 linked identities. No fixture passed the player-evidence
gate. Historical player-process ingestion follows the live backfill's recent
history phase; do not substitute the old sparse sample for an evaluated oracle.
`runs/research-ready-v1-player-gate-audit/manifest.json` retains the new gate and
the evolving capture snapshot; it does not replace the experiments' frozen
initial input or claim final recent-history completion. The earlier
`player-gate-check` snapshot counted unknown IDs in its duplicate-key reason;
it is superseded by this corrected audit, with the same zero-eligibility outcome.

All 221 tests pass. Tests cover unlinked IDs, incomplete
cross-provider participants, identity collisions and genuine duplicate keys.

## Current EFL edition verified

The official [2026/27 EFL regulations](https://images.gc.eflservices.co.uk/EFL+Regulations+%5BMASTER+VERSION%5D.pdf)
were captured through the repository fetcher into `runs/efl-rules-2026` at
2026-09-08T20:52:07.692189Z. The PDF identifies its edition on page 1; pages
28–31 confirm sections 9.1–9.9 and the Championship boundaries in 10.1.1(b) and
10.1.2(b). The retained SHA-256 is
`0ff9353d9fd8288fcca8c448c2d78e69050eed02b90bc8e7d8ece1e36acce630`.

The existing ranking implementation and automatic-promotion/playoff/relegation
boundaries match the current edition. The playoff field is explicitly six clubs
after the top two: fifth hosts eighth and sixth hosts seventh in quarter-finals;
third/fourth enter the two-legged semi-finals. This verifies qualification
boundaries, not an implemented playoff-tournament probability model.

`data/efl_rules_evidence.json` records reviewed sections, source timing/hash and
limits; simulation outputs include this evidence only for the matching season.
Readiness no longer treats the current edition as unverified. It admits only
regular-season ranks with explicit unresolved disciplinary-tie uncertainty, not
promotion-win probabilities. The first-42-match penalty-point comparison,
wrongful-dismissal reversals and twelve-point sending-off count still lack
forecast data. Do not claim those official procedures were applied to simulated
unresolved ties. The review does not automatically certify a future edition.

## Bounded roster-departure feasibility

`research/roster_transition.py` defines a deliberately limited candidate:
prior-season regular-match minutes lost through a coherent transfer chain
between season end and the next opener. This is recorded-departure exposure,
not complete squad turnover, arrival quality, or a reconstructed historical
registration list. No transfer response means unknown, not no departure. Missing
dates/endpoints, inconsistent chains and unordered same-day moves remain
unknown; the report retains lower/upper departure-share bounds. Same-day opener
moves are excluded because a date alone cannot establish pre-kickoff availability.
Retrieval timestamps never inherit transfer event dates.

`scripts/audit_roster_transition.py` audits only the recent window, excludes
missing prior divisions and incomplete/colliding prior exposure, and preserves
per-player reasons. Against the pinned player-gate snapshot it admits 0 of 132
candidate team-seasons: nine clubs lack a prior division in the two-league
window, and all other 123 retain unknown departure exposure (one also has
incomplete starter evidence). Mean unknown prior-minute share is 25.3%, ranging
from 0.72% to 78.6%. These counts are provisional while captures continue;
`runs/roster-transition-readiness.json` retains the evidence. Do not fit a variance
effect by treating those missing histories as unchanged squads.

All 225 tests pass, including coherent return transfers, cutoff isolation,
ambiguous chains, unknown-history bounds and actual retrieval filtering. The
regular-season-only minute correction was also checked with the three roster
tests and the complete live audit. A pooled constant-versus-departure variance
comparison still requires an admitted cohort; no adaptive dynamics or player
coefficients were added.

Backfill session `38720` exited normally after its 3,000-request invocation
budget at 20:54:32Z. It confirmed all 1,453 current-player histories complete.
The wider recent population remains incomplete. Session `59435` resumes the
same 2023–2026 scope with the existing 1,000-request daily reserve; do not launch
a concurrent writer. This is a verified terminal-and-resume transition, not a
restart caused by quiet output.
