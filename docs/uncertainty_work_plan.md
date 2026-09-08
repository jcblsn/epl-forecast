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
