# M6 candidate squads and expected minutes

The initial lineup layer distinguishes two types of evidence. `snapshot_squads`
verifies the existing immutable live snapshot checksums and uses the bootstrap
collection time for membership and availability. FPL membership is a squad proxy,
not an independently verified Premier League registration list. Removed players
and FPL unavailable (`u`) records are excluded; injuries and suspensions remain
candidates with uncertain availability. Archived `news_added` never substitutes
for collection time.

`PlayerHistory.retrospective_squad` instead uses each player's last recorded club
on strictly earlier UTC dates in the target season. It never reads the target
fixture to discover candidates, resets membership each season, and moves players
only after a past fixture records the new club. It cannot establish exact transfer
dates, registration, injury states or unrecorded unused players. All such squads
are labeled retrospective proxies with unknown publication times. A new season
therefore starts with anonymous replacements. That limitation is measured rather
than repaired with future information.

Season-specific IDs remain authoritative. FPL codes link exposures across seasons,
with one-to-one code/element checks within each season. This is a provider identity
assumption, not external biographical verification. Positions come from the
fixture-history row or the captured bootstrap; missing positions stay unknown.
Normalizing positions changes the processed dataset hash in the player audit.

Each draw selects eleven distinct starters from five explicit role formations,
using smoothed last-five start counts (minutes/90 where starts are unknown).
Availability is sampled first. Formation selection minimizes missing players;
unknown role-specific replacements fill remaining gaps. Up to nine available
reserves can supply at most five substitutions, each replacing the same role.
Starter and substitute minutes sum to 990, with 90 goalkeeper minutes and no
player exceeding 90. This is a full-strength regulation-time model; it does not
simulate red cards, added-time minutes or tactical role changes.

Start weights use two pseudo-observations with mean 0.3. Bench selection uses
the same weights. A reserve has substitution probability 0.65 (0.02 for keepers),
and substitute duration uses past bench minutes capped at 45, or a uniform
10–30-minute fallback. These are explicit initial modeling assumptions pending
chronological evaluation, not fitted player-quality estimates.

FPL next-round playing probability initializes availability; missing probabilities
use status defaults (available 1, doubtful/unknown 0.5, injured/suspended/not
available 0). Availability recovers linearly to 1 over 28 days from collection.
That is a bounded recovery assumption, not a medical estimate. Explicit scenarios
can instead hold a probability until a declared expiry. Scenario observations
must be known by the squad cutoff. Beyond expiry, the assumption has no effect.

Reproduce inputs and chronological lineup coverage with:

```sh
uv run python scripts/audit_players.py
uv run python scripts/evaluate_lineups.py --output runs/m6-lineups-v1
uv run pytest tests/test_players.py tests/test_lineups.py tests/test_live.py
```

The evaluation retains every candidate/outcome-union player prediction, including
zero predictions for newcomers missing from the pool. It reports starter coverage,
missing actual minutes, anonymous forecast minutes, minutes MAE and start Brier
score, including opening, major lineup-change and newcomer slices. Scores over
the union include unused players and must not be mistaken for starter-only scores.
Historical source values may contain later corrections. The layer is not yet
connected to club/player strength inference or the forecast product.

## Initial chronological evidence

The [retained report](experiments/m6/lineup_coverage.json) covers all 1,140
2023/24–2025/26 fixtures, 2,280 club-fixture sides, with 128 draws per side.
Candidate coverage is 97.15% of actual starters overall, 79.24% in each club's
first five fixtures, and 99.86% thereafter. Each first fixture has no prior-season
membership carried forward: its 990 minutes are anonymous. Opening-five missing
actual exposure averages 207.08 minutes per side, versus 1.69 later. This is a
known roster-evidence gap, not evidence that the missing players were unavailable.

Minutes MAE over the union of predicted and observed players is 22.38, and starter
Brier score is 0.12740. Four-or-more starter changes worsen those scores to 24.07
and 0.15160. These are initial absolute scores, not an improvement claim; a
chronological lineup baseline comparison remains necessary. Full predictions and
fixture-side diagnostics remain in `runs/m6-lineups-v1`, with hashes in the report.
