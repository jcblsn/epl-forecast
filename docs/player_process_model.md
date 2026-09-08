# Second attacking-player formulation: M7 oracle gate

M6-v1 remains the retained first player-information experiment. Its static,
goals-based player Quality coefficients are not the next architectural parent.
M7 remains the team xG parent; M8 remains parked. The current steering memo
supersedes the earlier requirement to settle M8 before this gate. The
[uncertainty budget](experiments/uncertainty_budget.md) and
[promotion-prior comparison](experiments/promotion_transition.md) now provide
the requested team-level evidence. They do not establish player gains or justify
adaptive dynamics.

The existing M6 `PlayerQualityFilter._augment_design` assigns each scalar player
coefficient to both home and away score rates with opposite signs. Its oracle
score projection uses the same symmetric direction. Reusing it unchanged would
violate the attacking-only formulation below. Existing lineup sampling and
cutoff handling may be reused, but both training and forecast player designs
must give a club's players zero direct coefficient in its opponent's rate.

## Identity and roles

The [identity audit](experiments/m8/player_identity.json) joins the pinned
36-match Understat sample to historical FPL appearances using canonical fixture,
club and an exact normalized name. It propagates a link across appearances only
through an unambiguous stable FPL player code. Conflicting codes raise an error;
ambiguous names remain unresolved. Explicit aliases are supported but none are
silently inferred by fuzzy matching.

The sample contains 1,033 appearances and 721 Understat IDs. It links 760
appearances representing 545 IDs; 166 appearances predate FPL fixture coverage,
and 107 remain unresolved. The compressed record artifact retains source hashes,
linked IDs, candidate names, process fields and role evidence. This is an audited
foundation, not exhaustive identity coverage and not an operational mapping.
Resolve and verify remaining identities across the intended fitting population
before relying on a new player layer operationally.

Understat match roles and FPL season positions are different measurements. Keep
both: 24 linked appearances disagree in their broad role classifications.
Understat substitutes have no observed match role; an available FPL position is
an explicitly labeled fallback, not reconstructed tactical knowledge. There are
120 appearances without even a broad process role after these rules. Unknown
roles must be pooled/marginalized rather than silently classified as attackers.

League-match xG is not consistently the sum of additive player/shot xG. Retain
separate provider fields; never force player xG or xA to sum to the team field.
The player data are retrospective participation evidence, not proof of what a
forecaster knew before an old kickoff.

## Proposed model and test

Preserve persistent club/system Quality and Tilt. Add player contributions only
to the team's attacking process log rate: a lineup exposure vector, integrated
over uncertain minutes, multiplies pooled player attacking coefficients. The
opponent's player coefficients do not enter the defending rate. Persistent club
state absorbs tactical and defensive contributions that these data cannot
credibly attribute to individuals.

Use role-aware zero-centered Normal priors for player deviations, with strongly
pooled role scales. Center lineup contributions relative to a team's reference
squad so club and player level do not freely trade off. Carry club/player
covariance, coefficient shrinkage and minute uncertainty through forecasts and
season paths. Transfers move player contributions while persistent system state
stays with the club. Do not add player Tilt or symmetric defensive coefficients.

Use xG, xA and shot involvement to explain process generation, not as independent
copies of the same team observation. A coherent candidate can model player/shot
involvement as conditional process allocation marks, conditional on the common
team process, while estimating a separate provider relation for league-match
xG. Its allocation likelihood must not multiply an independent team-total
likelihood by an equivalent sum of player totals. Validate that provider relation
on exhaustive, reconciled fixtures before fitting it; the current sample does
not establish it. Goals remain downstream of the team observation model.

Evaluate the team-only process parent, the attacking-player process candidate,
and the same candidate with actual minutes on identical chronological fixtures.
Use the retained pre-closing and closing markets in every major comparison.
Record oracle/known-minutes forecasts as nondeployable. Strong oracle gains
without forecast-lineup gains indicate an information/lineup problem. Failure
with actual lineups calls for reassessing the player representation before
adding complexity. Report opening/promoted, large lineup-change and unseen-player
slices, and verify directional responses and coefficient identification.

The earlier batch supplied the mapping audit, role rules, representation and
decision protocol. The current batch is capturing the bounded 2023/24–2025/26
canonical process population. Exact retained provider names may establish
unambiguous links within the same fixture/team; future name and stable-ID
evidence is excluded. The old 36-match sample above remains historical evidence,
not the current experiment's cohort.

The machine-readable `player_oracle_evidence` cohort additionally requires team
xG, starter-minute coverage, linked process identities and matching positive-
exposure participants, excluding unresolved identity contradictions. This is a
necessary data gate, not validation of the proposed allocation likelihood.
Publication, reconciliation, matched three-condition evaluation and actual
empirical oracle results are still outstanding. No player-process predictive
gain is claimed for an unfitted model.
