# Retained information and uncertainty work

The September 8, 2026 batch supplied the team-level evidence used by the
[architecture work plan](architecture_next_phase.md). That plan supersedes the
old research ordering, the restriction against a new model family, and the
requirement to use M7 as the architectural parent. M2 remains operational.

## Evidence and reusable machinery

| Work | Retained evidence | Reusable implementation |
| --- | --- | --- |
| Matched uncertainty attribution | [Uncertainty budget](experiments/uncertainty_budget.md) | `scripts/evaluate_uncertainty_ladder.py` |
| Sensor persistence and complementarity | [Information value](experiments/information_value.md) | `scripts/evaluate_information_value.py` |
| Promoted-club priors | [Promotion transition](experiments/promotion_transition.md) | `scripts/evaluate_promotion_transition.py` |
| Immutable research inputs and eligibility | `runs/research-ready-v1-initial/manifest.json` and later distinct freezes | `scripts/freeze_research.py` |
| Recorded roster departures | `runs/roster-transition-readiness.json` | `scripts/audit_roster_transition.py` |
| Historical player-process capture | [Player layer](experiments/player_layer.md) | `scripts/stage_player_process.py` |

The original eleven-season uncertainty ladder is retained in
`runs/uncertainty-ladder-v1`; information-value and promotion results are in
`runs/information-value-v1` and `runs/promotion-transition-v1`. Reports contain
the input hashes, comparisons and limitations. Local provider evidence and runs
are ignored by Git and need separate backups.

Current-state uncertainty earned early-season support. Future innovations did
not justify adaptive elaboration in that batch. A calibrated M2 season-dependence
arm preserved M2 match probabilities and improved some preseason distribution
scores. The sensor and promotion results did not establish a reliable incremental
benefit from process statistics beyond the tested controls. These are findings
about those implementations, not constraints on the new common hierarchy.

## Data and interpretation boundaries

The frozen research reader checks publication and Parquet hashes and separates
strict retrieval cutoffs from the explicit next-day historical availability
assumption. A historical backfill does not establish old pre-match availability.
Eligibility is per fixture and signal; a successful capture or publication does
not certify every downstream model.

Recorded roster departure is the prior-season minute share associated with a
coherent transfer chain before the next opener. It is not full squad turnover or
arrival quality. Missing histories, dates, endpoints and ambiguous chains remain
unknown. The initial audit admitted no complete cohort; any new comparison must
use a fresh coverage audit rather than treat unknown histories as unchanged squads.

The player oracle gate additionally checks team xG, usable starter minutes,
linked identities, matching positive-exposure participants and identity collisions.
It does not validate a proposed player/team likelihood. The subsequent standalone
player report supersedes the old staging-session and sparse-sample checkpoints.
Raw team xG and additive player process remain different provider measurements.

Shared forecast/evaluation provenance records code state, lockfile and runner
hashes, Python/dependency versions and actual interpreter/application arguments.
It does not claim to recover an unobserved shell wrapper. Different executions
retain separate immutable records.

## Competition rules and remaining product limits

The retained official 2026/27 EFL regulation capture is described by
`data/efl_rules_evidence.json` and `runs/efl-rules-2026`. Its SHA-256 is
`0ff9353d9fd8288fcca8c448c2d78e69050eed02b90bc8e7d8ece1e36acce630`.
The review covered ranking sections 9.1–9.9 and Championship boundaries in
10.1.1(b) and 10.1.2(b). It established the season's six playoff qualifiers after
the top two and the fifth/eighth, sixth/seventh quarter-final arrangement.
This is retained rule evidence, not a new verification of current external rules.

Existing regular-season projections do not model the playoff tournament or
claim promotion-win probabilities. Unresolved disciplinary criteria are disclosed;
unknown discipline is not zero. Full joint simulation must address these limits,
verify the applicable rules and report its explicit conditional assumptions.

Twelve-hour prospective collection is documented in [live operations](live.md).
An experiment claiming late injury or confirmed-lineup information needs captures
that actually observe those changes. Old session handles and process IDs are
historical checkpoints, not evidence that a job is running now.
