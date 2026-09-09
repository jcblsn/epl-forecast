# Standalone player-process layer

Status: in progress. This file records the design, the data gate and the evidence
as it is produced. No predictive claim in it is settled until the evaluation tables
below are filled from a frozen run.

The question this batch asks is whether a cutoff-safe, time-varying, uncertain
representation of player contribution can be estimated from retained evidence in a
form that survives a change of club, without assigning an elite player's ordinary
contribution to his club. It deliberately does not ask how a club model should
consume the answer.

## What is separated from what

Estimation of portable player information is separated from application of that
information to a club. The retained V1 time-local prior learns player means through
a match likelihood in which actual personnel are centred against a club's recent
reference personnel. That centring solves a real double-counting problem downstream
and is not changed here. It is simply no longer the mechanism through which player
information is discovered, because an ever-present player produces almost no
variation in lineup share for it to learn from.

Every candidate in this batch instead predicts a player's own subsequent attacking
process, conditioned on the exposure he actually received. Conditioning on realized
exposure isolates the process rate from lineup forecasting, which is out of scope
for this batch; it also makes every score here explicitly nondeployable as a match
forecast.

## Provider semantics resolved before choosing features

Two findings from `scripts/audit_player_signals.py` are load-bearing.

API-FOOTBALL omits several count fields when the value is zero. In a fully detailed
payload, `passes_total` is present on 98.7% of appearances but `goals` on 7.9%,
`shots` on 38.6% and `key_passes` on 40.6%. A retained payload confirms it directly:
a player with `goals.total: null` and `shots.total: null` alongside a teammate with
`goals.total: 1` and `shots.total: 1`. Cross-checking against the independent
Understat mark agrees: of 314 appearances where the API shot count is null and an
Understat record exists, 276 have exactly zero Understat shots.

Read as missing rather than zero, these rates divide only by the exposure in which
the event occurred. Every player's rate is inflated and the differences between
players are compressed — precisely the signal a striker representation depends on.
The layer therefore treats a provider null as a zero for these fields and keeps a
genuine missing value only where the retained normalization never published the
field at all.

The retained `pass_accuracy` string is resolved as a completed-pass count, not a
percentage. Across 2,982 appearances where both are present it never exceeds
`passes_total`, correlates with it at 0.984, and exceeds 100 only where the total
does. The earlier decision to exclude it was correct under the earlier evidence; the
unit is now established and the field is admissible as a completion rate.

## Publication gap in the retained appearance fields

The detailed statistics are present in the retained raw payloads for historical
seasons but reach canonical rows only at the later normalization. Before the replay
described below, `passes_total`, `rating`, `key_passes`, `tackles`, `interceptions`,
`duels` and `dribbles` were published for 2026/27 only and were entirely absent from
2016/17 through 2025/26. That is a publication gap, not a capture gap, and it is why
a full replay of retained requests is part of this batch's data gate rather than a
new provider.

## Candidates

| Candidate | What it reads |
| --- | --- |
| `pooled_role` | Role population rate only; the player contributes nothing. |
| `recent_raw` | Recent shrunk per-90 rate, the naive form of "he is in form". |
| `long_run` | Long-horizon shrunk per-90 rate. |
| `recent_long` | Both horizons, so recent information must earn its weight. |
| `long_plus_env` | Long-run rate together with the club environment it will play in. |
| `context_share` | Portable share of team attacking process times the target club environment. |
| `context_share_recent` | Share on both horizons times the target club environment. |
| `api_only` | The V1 API-only feature family, with no Understat process evidence. |
| `api_rating` | The V1 API-only family plus the proprietary rating, as an ablation. |

`long_plus_env` exists so that `context_share` is not credited for merely knowing the
target club. The two see the same club environment; only the decomposition differs.

Shooting and creation are kept separate throughout. Understat xG and xA are related
marks of one attacking process — a single shot can generate xG for the shooter and xA
for its creator — so they are never added together by convention. Any combined score
has to state what it represents and earn its aggregation.

## Evaluation

Cases are (player, cutoff) pairs on a monthly grid. The target is the player's process
over the following horizon with his realized exposure. The mapping from features to a
rate is a ridge-penalised Poisson fit, refit at every scored cutoff on cases whose
target window had already closed, so no case is ever trained on evidence from its own
future. Predictive distributions combine parameter uncertainty with an empirical
multiplicative residual law stratified by target exposure and by evidence depth, and
are scored with CRPS, a proper score, alongside empirical 50% and 90% interval
coverage. Paired comparisons resample by player, so an ever-present player counts once
rather than as many independent cases.

Transfer portability is a separate diagnostic. A pre-move estimate is frozen at the day
of a player's first appearance for a new club and scored against his early process
there. Observed club changes are retrospective labels for portability; they are not
claims that a transfer was known to any forecaster at the cutoff.

## Results

Pending the frozen run.

## Decision

Pending.
