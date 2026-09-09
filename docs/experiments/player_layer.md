# Standalone player-process layer

This batch treats the player layer as an independent research product. It asks
whether a cutoff-safe, time-varying, uncertain representation of player contribution
can be estimated from retained evidence in a form that survives a change of club and
does not assign an elite player's ordinary contribution to his club. It deliberately
does not ask how a club, match or season model should consume the answer, and nothing
here is wired into one.

## What is separated from what

Estimation of portable player information is separated from application of that
information to a club.

The retained V1 time-local prior learns player means through a match likelihood in
which actual personnel are centred against a club's recent reference personnel. That
centring solves a real downstream double-counting problem and is unchanged by this
batch. It is simply no longer the mechanism through which player information is
discovered: an ever-present player produces almost no variation in lineup share, so
there is very little for it to learn from. That is a property of the discovery
mechanism, not of the player.

Every candidate here instead predicts a player's own subsequent attacking process,
conditioned on the exposure he actually received. Conditioning on realized exposure
isolates the process rate from lineup forecasting, which is out of scope for this
batch. It also makes every score here explicitly nondeployable as a match forecast.

## The data gate

Historical Understat match-player capture was completed from the retained staging
process and published to the canonical store: 1,140 Premier League fixtures across
2023/24, 2024/25 and 2025/26, all 380 finished fixtures in each season, joining the
30 current-season fixtures already held.

The gate required deterministic identity linkage, no silent many-to-one collapse,
valid positive exposure and explicit unresolved mappings. All four hold.

| Season | Fixtures with process | Records | Linked | Unlinked | Linked players | Invalid exposure | Records missing marks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023/24 | 380 / 380 | 11,384 | 96.85% | 359 | 550 | 0 | 0 |
| 2024/25 | 380 / 380 | 11,567 | 97.61% | 276 | 547 | 0 | 0 |
| 2025/26 | 380 / 380 | 11,490 | 96.68% | 381 | 519 | 0 | 0 |
| 2026/27 | 30 / 30 | 929 | 97.42% | 24 | 378 | 0 | 0 |

Across the whole population there are **zero** many-to-one collisions — no two
Understat records ever reach the same canonical player in one fixture — and **zero**
positive-exposure disagreements, meaning every player the process source records as
having played also appears in the API appearance evidence for that fixture. A record
with more than one Understat id mapping to one canonical player is treated as an
unresolved identity and excluded, never summed.

Only 36 Understat ids never link, covering 1,040 records — 3% of the population. They
are not random. Every one is a name the exact normalized-token rule cannot bridge: a
single-name provider entry (`Toti`), a compound surname the two sources split
differently (`Jamie Bynoe-Gittens`, `Joe Ayodele-Aribo`), or a transliteration
(`Djordje Petrovic`, `Ferdi Kadioglu`, `Altay Bayindir`, `Hákon Valdimarsson`). One
has no retained provider name at all. The design refuses to close that gap by fuzzy
matching, so the audit names them from the retained payloads and they stay excluded.

The replay materially improved linkage. Before it, 269 ids covering 1,440 records were
unresolved and 2026/27 linked at only 54%; republishing every retained request at the
current normalization brought 2026/27 to 97.4% and cut the unresolved set to 36 ids.
The linkage rule may only use name evidence retained at or before the process
payload's own retrieval time, and the replay establishes that ordering consistently
across the whole store rather than in the order the live collector happened to run.

### Two different gates, and which one this layer needs

The repository's existing `player_oracle_evidence` gate is stricter than the one
above. It requires a fixture to be *wholly* complete: every process identity linked,
and the positive-exposure participants agreeing exactly between the two providers.
On the frozen manifest it admits 461 of the 1,170 captured fixtures — 148 in 2023/24,
183 in 2024/25 and 117 in 2025/26 — and 709 of the exclusions are fixtures where a
single unlinked identity fails both conditions at once.

That gate is the right one for a future allocation likelihood, which has to divide a
team's process among a complete set of participants and cannot tolerate a missing
one. It is not the gate this layer needs. Estimating a player's own rate per 90
requires only that his own records are correctly linked and his exposure valid; a
teammate whose identity is unresolved reduces the evidence available about that
teammate and about nobody else. This layer therefore drops unlinked records and keeps
the fixture, and the 3% of unresolved records cost 3% of the evidence rather than 60%
of the fixtures. The distinction is worth carrying forward: the same population is
research-ready for a per-player process layer and not yet research-ready for a
per-fixture allocation model.

## Signal audit: what the providers actually publish

Two findings changed the representation and are load-bearing.

**A provider null is a zero, not a missing value.** API-FOOTBALL omits several count
fields when the value is zero. Within a fully detailed payload, `passes_total` is
present on 98.7% of appearances but `goals` on 7.9%, `shots` on 38.6%, `key_passes`
on 40.6% and `saves` on 15.8%. A retained payload shows it directly: one player has
`goals.total: null` and `shots.total: null` while a teammate in the same fixture has
`goals.total: 1` and `shots.total: 1`. An independent check agrees — of 314
appearances where the API shot count is null and an Understat record exists, 276 have
exactly zero Understat shots.

Read as missing rather than zero, a rate divides only by the exposure in which the
event occurred. Every player's rate is inflated and the differences between players
are compressed, which attacks precisely the signal a striker representation depends
on. The layer now treats these nulls as zero and keeps a genuine missing value only
where the retained normalization never published the field at all.

**The pass-accuracy string is a completed-pass count.** Across 2,982 appearances
where both are present it never exceeds `passes_total`, correlates with it at 0.984,
and exceeds 100 only where the total does. A percentage reading is excluded. The
earlier decision to exclude the field was correct under the earlier evidence; the
unit is now resolved and the field is admissible as a completion rate.

**A publication gap, not a capture gap.** The detailed statistics are present in the
retained raw payloads for historical seasons but reached canonical rows only at the
later normalization. Before this batch's replay, `passes_total`, `rating`,
`key_passes`, `tackles`, `interceptions`, `duels` and `dribbles` were published for
2026/27 only and were entirely absent from 2016/17 through 2025/26. Replaying every
retained request at the current normalization closed that gap without contacting any
provider.

**Stability, not just availability.** Within-player-season odd/even split-half
reliability of per-90 rates, stepped up by Spearman-Brown, ranks the fields on the
frozen population:

| Field | Reliability | Player-seasons | | Field | Reliability | Player-seasons |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| `passes_total` | 0.859 | 9,705 | | `key_passes` | 0.552 | 6,994 |
| `rating` | 0.748 | 9,642 | | `fouls_committed` | 0.523 | 7,954 |
| `duels_total` | 0.725 | 9,508 | | `goals` | 0.455 | 672 |
| `assists` | 0.692 | 2,240 | | `interceptions` | 0.432 | 7,025 |
| `dribbles_attempted` | 0.674 | 7,520 | | `tackles` | 0.381 | 6,439 |
| `shots_on_target` | 0.665 | 5,468 | | `red_cards` | 0.067 | 9,759 |
| `shots` | 0.607 | 7,014 | | `yellow_cards` | 0.063 | 9,759 |

Disciplinary counts carry essentially nothing about the player and are excluded.
Tackles and interceptions are weak enough to leave out of an attacking layer.

The process marks are less stable than the API counts they sit beside: Understat
shots 0.452, xG 0.353 and xA only 0.112, over 1,290 player-seasons. That last number
matters. Creation is intrinsically the noisiest of the three components, and it
predicts the outcome below where the API count representation beats the process
representation on exactly that component.

## Candidates

Ten matched representations, each predicting the same targets on the same cases.

| Candidate | What it reads |
| --- | --- |
| `pooled_role` | Role population rate only; the player contributes nothing. |
| `recent_raw` | Recent shrunk per-90 rate — the naive form of "he is in form". |
| `long_run` | Long-horizon shrunk per-90 rate. |
| `recent_long` | Both horizons, so recent information must earn its weight. |
| `long_plus_env` | Long-run rate together with the club environment it will play in. |
| `context_share` | Portable share of team attacking process times the target club environment. |
| `context_share_recent` | Share on both horizons times the target club environment. |
| `combined_long` | Long-run rate of the summed xG+xA mark. |
| `api_only` | The V1 API-only feature family, with no Understat process evidence. |
| `api_rating` | The V1 API-only family plus the proprietary rating, as an ablation. |

The context-adjusted candidate models a player's attacking mark per unit of *team*
attacking process generated while he was on the pitch, and predicts by multiplying
that portable share by the target club's own pre-cutoff attacking rate. Half-lives
are 45 and 240 days; rates are shrunk toward a role population with a fixed prior
strength; every feature is a clipped log ratio to its role population. Nothing here
was tuned against a leaderboard.

`long_plus_env` exists so that `context_share` cannot be credited merely for knowing
which club the player will be at. Both see the same club environment; only the
decomposition differs.

Shooting and creation are kept separate throughout. Understat xG and xA are related
marks of one attacking process — one shot can generate xG for the shooter and xA for
its creator — so they are never added by convention. `combined_long` exists to test
whether the conventional sum earns its aggregation.

## Evaluation

The frozen research manifest is `runs/research-ready-v2-player-layer/manifest.json`.
Every number below comes from that snapshot.

Cases are (player, cutoff) pairs on a monthly grid from September 2023, scored from
January 2025. The target is the player's process over the following horizon at his
realized exposure. The mapping from features to a rate is a ridge-penalised Poisson
fit, refit at every scored cutoff using only cases whose target window had already
closed, so no case is ever trained on evidence from its own future.

Predictive distributions combine parameter uncertainty from the fit with an empirical
multiplicative residual law stratified by target exposure and by evidence depth. They
are scored with CRPS, a proper score, alongside empirical 50% and 90% interval
coverage. Paired comparisons resample by player, so an ever-present player counts
once rather than as many independent cases.

Transfer portability is a separate diagnostic. A pre-move estimate is frozen on the
day of a player's first appearance for a new club — the appearance itself is not
eligible evidence at that cutoff — and scored against his early process there.
Observed club changes are retrospective labels for portability; they are not claims
that a transfer was known to any forecaster at the cutoff.

The 90-day horizon is reported below. A 180-day horizon over the same design
reproduces every conclusion with larger magnitudes: on shooting, the pooled role
prior costs +0.127 [+0.100, +0.158], the summed mark costs +0.034 [+0.024, +0.045],
and the API-only family is +0.007 with an interval spanning zero; on creation the
API-only family gains −0.011 [−0.017, −0.005]. Its artifacts are in
`runs/player-layer-h180`.

## Results

### Shooting (Understat xG)

9452 cases built, 18 scored cutoffs, 79 observed club changes. A starred interval excludes zero.

Chronological, horizon 90 days.

| Candidate | CRPS | MAE | 50% cover | 90% cover | Relative width | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 0.39625 | 0.5646 | 0.517 | 0.945 | 2.73 | +0.0696 [+0.0550, +0.0857] * |
| `recent_raw` | 0.35072 | 0.4735 | 0.533 | 0.942 | 2.65 | +0.0241 [+0.0187, +0.0298] * |
| `long_run` | 0.32661 | 0.4377 | 0.531 | 0.947 | 2.59 | reference |
| `recent_long` | 0.32528 | 0.4364 | 0.531 | 0.946 | 2.59 | -0.0013 [-0.0023, -0.0004] * |
| `long_plus_env` | 0.32636 | 0.4373 | 0.528 | 0.948 | 2.56 | -0.0003 [-0.0013, +0.0008] |
| `context_share` | 0.32451 | 0.4372 | 0.537 | 0.949 | 2.57 | -0.0021 [-0.0044, +0.0000] |
| `context_share_recent` | 0.32327 | 0.4353 | 0.533 | 0.948 | 2.57 | -0.0033 [-0.0059, -0.0009] * |
| `combined_long` | 0.34489 | 0.4613 | 0.519 | 0.941 | 2.70 | +0.0183 [+0.0135, +0.0232] * |
| `api_only` | 0.33076 | 0.4444 | 0.518 | 0.934 | 2.52 | +0.0041 [-0.0005, +0.0084] |
| `api_rating` | 0.33038 | 0.4436 | 0.519 | 0.934 | 2.53 | +0.0038 [-0.0008, +0.0082] |

Frozen pre-move estimate against early new-club process.

| Candidate | CRPS | MAE | 50% cover | 90% cover | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 0.98279 | 1.5463 | 0.582 | 0.975 | +0.2508 [+0.1423, +0.3690] * |
| `recent_raw` | 0.85860 | 1.2806 | 0.557 | 0.962 | +0.1266 [+0.0553, +0.2008] * |
| `long_run` | 0.73203 | 1.0186 | 0.557 | 0.962 | reference |
| `recent_long` | 0.72897 | 1.0219 | 0.544 | 0.962 | -0.0031 [-0.0173, +0.0125] |
| `long_plus_env` | 0.73885 | 1.0451 | 0.532 | 0.962 | +0.0068 [-0.0038, +0.0188] |
| `context_share` | 0.80099 | 1.2178 | 0.570 | 0.975 | +0.0690 [+0.0245, +0.1208] * |
| `context_share_recent` | 0.79378 | 1.2101 | 0.532 | 0.975 | +0.0618 [+0.0190, +0.1098] * |
| `combined_long` | 0.80009 | 1.0903 | 0.532 | 0.962 | +0.0681 [+0.0277, +0.1094] * |
| `api_only` | 0.75790 | 1.0981 | 0.494 | 0.975 | +0.0259 [-0.0346, +0.1005] |
| `api_rating` | 0.74703 | 1.0891 | 0.494 | 0.975 | +0.0150 [-0.0395, +0.0797] |

CRPS by slice.

| Candidate | all | changed_club | low_history | high_history | role_FWD | role_MID | role_DEF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pooled_role` | 0.39625 | 0.32278 | 0.33378 | 0.45119 | 0.80075 | 0.44614 | 0.19706 |
| `recent_raw` | 0.35072 | 0.29117 | 0.32106 | 0.38538 | 0.73387 | 0.36351 | 0.19633 |
| `long_run` | 0.32661 | 0.26258 | 0.31701 | 0.35467 | 0.68430 | 0.33384 | 0.18862 |
| `recent_long` | 0.32528 | 0.26044 | 0.31689 | 0.35280 | 0.67981 | 0.33288 | 0.18851 |
| `long_plus_env` | 0.32636 | 0.26131 | 0.31336 | 0.35609 | 0.68386 | 0.33383 | 0.18809 |
| `context_share` | 0.32451 | 0.26938 | 0.30525 | 0.35414 | 0.68150 | 0.33021 | 0.18799 |
| `context_share_recent` | 0.32327 | 0.26730 | 0.30537 | 0.35281 | 0.67709 | 0.32940 | 0.18797 |
| `combined_long` | 0.34489 | 0.27679 | 0.32577 | 0.37561 | 0.72603 | 0.34844 | 0.20109 |
| `api_only` | 0.33076 | 0.25433 | 0.31671 | 0.36613 | 0.69500 | 0.33705 | 0.19129 |
| `api_rating` | 0.33038 | 0.25332 | 0.31724 | 0.36544 | 0.69357 | 0.33519 | 0.19316 |
| cases | 4920 | 109 | 614 | 1753 | 965 | 1841 | 1739 |

Persistence of the residual the mapping does not explain.

| Candidate | Players | Half-split correlation (95% CI) | Persistent sd | Noise sd |
| --- | ---: | --- | ---: | ---: |
| `pooled_role` | 464 | +0.608 [+0.542, +0.668] | 0.575 | 0.471 |
| `recent_raw` | 464 | +0.374 [+0.284, +0.461] | 0.357 | 0.475 |
| `long_run` | 464 | +0.254 [+0.156, +0.348] | 0.274 | 0.495 |
| `recent_long` | 464 | +0.250 [+0.153, +0.344] | 0.273 | 0.499 |
| `long_plus_env` | 464 | +0.253 [+0.156, +0.348] | 0.272 | 0.494 |
| `context_share` | 464 | +0.263 [+0.167, +0.360] | 0.279 | 0.494 |
| `context_share_recent` | 464 | +0.256 [+0.159, +0.353] | 0.278 | 0.500 |
| `combined_long` | 464 | +0.419 [+0.337, +0.499] | 0.395 | 0.480 |
| `api_only` | 464 | +0.316 [+0.225, +0.408] | 0.317 | 0.483 |
| `api_rating` | 464 | +0.314 [+0.223, +0.407] | 0.317 | 0.482 |

### Creation (Understat xA)

9452 cases built, 18 scored cutoffs, 79 observed club changes. A starred interval excludes zero.

Chronological, horizon 90 days.

| Candidate | CRPS | MAE | 50% cover | 90% cover | Relative width | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 0.29457 | 0.4350 | 0.538 | 0.946 | 2.85 | +0.0369 [+0.0273, +0.0481] * |
| `recent_raw` | 0.27150 | 0.3867 | 0.529 | 0.941 | 2.78 | +0.0138 [+0.0103, +0.0175] * |
| `long_run` | 0.25768 | 0.3618 | 0.541 | 0.948 | 2.89 | reference |
| `recent_long` | 0.25767 | 0.3619 | 0.542 | 0.948 | 2.91 | -0.0000 [-0.0005, +0.0005] |
| `long_plus_env` | 0.25763 | 0.3616 | 0.541 | 0.949 | 2.87 | -0.0001 [-0.0010, +0.0008] |
| `context_share` | 0.25676 | 0.3617 | 0.546 | 0.952 | 2.88 | -0.0009 [-0.0022, +0.0003] |
| `context_share_recent` | 0.25666 | 0.3614 | 0.545 | 0.952 | 2.89 | -0.0010 [-0.0024, +0.0003] |
| `combined_long` | 0.27447 | 0.3922 | 0.538 | 0.948 | 3.03 | +0.0168 [+0.0111, +0.0228] * |
| `api_only` | 0.25308 | 0.3455 | 0.518 | 0.939 | 2.81 | -0.0046 [-0.0071, -0.0020] * |
| `api_rating` | 0.25289 | 0.3434 | 0.516 | 0.941 | 2.85 | -0.0048 [-0.0074, -0.0023] * |

Frozen pre-move estimate against early new-club process.

| Candidate | CRPS | MAE | 50% cover | 90% cover | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 0.58006 | 0.8984 | 0.633 | 0.987 | +0.0588 [+0.0146, +0.1007] * |
| `recent_raw` | 0.55540 | 0.8311 | 0.557 | 0.987 | +0.0341 [-0.0027, +0.0700] |
| `long_run` | 0.52131 | 0.7452 | 0.646 | 0.975 | reference |
| `recent_long` | 0.52209 | 0.7429 | 0.646 | 0.975 | +0.0008 [-0.0046, +0.0065] |
| `long_plus_env` | 0.52059 | 0.7426 | 0.658 | 0.975 | -0.0007 [-0.0088, +0.0070] |
| `context_share` | 0.56638 | 0.8433 | 0.608 | 0.962 | +0.0451 [+0.0150, +0.0773] * |
| `context_share_recent` | 0.56969 | 0.8500 | 0.557 | 0.962 | +0.0484 [+0.0166, +0.0836] * |
| `combined_long` | 0.53890 | 0.7746 | 0.646 | 0.975 | +0.0176 [-0.0254, +0.0602] |
| `api_only` | 0.48475 | 0.6740 | 0.595 | 0.962 | -0.0366 [-0.0613, -0.0144] * |
| `api_rating` | 0.47870 | 0.6623 | 0.620 | 0.949 | -0.0426 [-0.0665, -0.0205] * |

CRPS by slice.

| Candidate | all | changed_club | low_history | high_history | role_FWD | role_MID | role_DEF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pooled_role` | 0.29457 | 0.28386 | 0.22474 | 0.32856 | 0.33602 | 0.39287 | 0.21936 |
| `recent_raw` | 0.27150 | 0.27666 | 0.21693 | 0.29217 | 0.31645 | 0.35853 | 0.20258 |
| `long_run` | 0.25768 | 0.26302 | 0.21315 | 0.28006 | 0.29997 | 0.34270 | 0.18999 |
| `recent_long` | 0.25767 | 0.26229 | 0.21297 | 0.28094 | 0.29996 | 0.34305 | 0.18961 |
| `long_plus_env` | 0.25763 | 0.26485 | 0.21063 | 0.28190 | 0.29803 | 0.34375 | 0.18980 |
| `context_share` | 0.25676 | 0.27895 | 0.20987 | 0.28041 | 0.29860 | 0.34177 | 0.18912 |
| `context_share_recent` | 0.25666 | 0.27886 | 0.20976 | 0.28085 | 0.29880 | 0.34174 | 0.18876 |
| `combined_long` | 0.27447 | 0.26327 | 0.21580 | 0.30488 | 0.34369 | 0.35494 | 0.20076 |
| `api_only` | 0.25308 | 0.26166 | 0.20765 | 0.27829 | 0.29493 | 0.33712 | 0.18650 |
| `api_rating` | 0.25289 | 0.26052 | 0.20737 | 0.27877 | 0.29644 | 0.33628 | 0.18606 |
| cases | 4920 | 109 | 614 | 1753 | 965 | 1841 | 1739 |

Persistence of the residual the mapping does not explain.

| Candidate | Players | Half-split correlation (95% CI) | Persistent sd | Noise sd |
| --- | ---: | --- | ---: | ---: |
| `pooled_role` | 464 | +0.612 [+0.550, +0.668] | 0.614 | 0.490 |
| `recent_raw` | 464 | +0.366 [+0.276, +0.455] | 0.385 | 0.508 |
| `long_run` | 464 | +0.250 [+0.148, +0.348] | 0.303 | 0.527 |
| `recent_long` | 464 | +0.247 [+0.145, +0.345] | 0.302 | 0.530 |
| `long_plus_env` | 464 | +0.253 [+0.154, +0.350] | 0.304 | 0.526 |
| `context_share` | 464 | +0.254 [+0.153, +0.354] | 0.305 | 0.527 |
| `context_share_recent` | 464 | +0.251 [+0.149, +0.351] | 0.305 | 0.529 |
| `combined_long` | 464 | +0.441 [+0.361, +0.521] | 0.451 | 0.510 |
| `api_only` | 464 | +0.316 [+0.225, +0.408] | 0.344 | 0.508 |
| `api_rating` | 464 | +0.311 [+0.219, +0.403] | 0.340 | 0.509 |

### Shot volume (Understat shots)

9452 cases built, 18 scored cutoffs, 79 observed club changes. A starred interval excludes zero.

Chronological, horizon 90 days.

| Candidate | CRPS | MAE | 50% cover | 90% cover | Relative width | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 2.29131 | 3.0853 | 0.519 | 0.954 | 2.17 | +0.4767 [+0.3852, +0.5669] * |
| `recent_raw` | 1.94469 | 2.5212 | 0.512 | 0.946 | 2.03 | +0.1301 [+0.1027, +0.1567] * |
| `long_run` | 1.81459 | 2.3464 | 0.526 | 0.944 | 1.97 | reference |
| `recent_long` | 1.81549 | 2.3520 | 0.524 | 0.944 | 1.97 | +0.0009 [-0.0016, +0.0034] |
| `long_plus_env` | 1.81370 | 2.3435 | 0.527 | 0.943 | 1.96 | -0.0009 [-0.0056, +0.0040] |
| `context_share` | 1.81630 | 2.3547 | 0.536 | 0.949 | 1.97 | +0.0017 [-0.0167, +0.0204] |
| `context_share_recent` | 1.81958 | 2.3603 | 0.535 | 0.947 | 1.97 | +0.0050 [-0.0144, +0.0246] |
| `combined_long` | 1.96393 | 2.5333 | 0.517 | 0.944 | 2.10 | +0.1493 [+0.1003, +0.2009] * |
| `api_only` | 1.80692 | 2.3174 | 0.511 | 0.936 | 1.92 | -0.0077 [-0.0268, +0.0120] |
| `api_rating` | 1.80542 | 2.3131 | 0.509 | 0.936 | 1.93 | -0.0092 [-0.0279, +0.0101] |

Frozen pre-move estimate against early new-club process.

| Candidate | CRPS | MAE | 50% cover | 90% cover | CRPS − long_run (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| `pooled_role` | 5.40199 | 7.5050 | 0.582 | 0.987 | +1.3807 [+0.7791, +2.0524] * |
| `recent_raw` | 4.46996 | 5.9721 | 0.595 | 0.962 | +0.4487 [+0.0423, +0.8566] * |
| `long_run` | 4.02128 | 5.5655 | 0.582 | 0.975 | reference |
| `recent_long` | 4.03404 | 5.6140 | 0.595 | 0.949 | +0.0128 [-0.0455, +0.0776] |
| `long_plus_env` | 3.98607 | 5.4735 | 0.595 | 0.975 | -0.0352 [-0.0837, +0.0152] |
| `context_share` | 4.83011 | 7.3392 | 0.557 | 0.975 | +0.8088 [+0.3697, +1.3131] * |
| `context_share_recent` | 4.87817 | 7.4089 | 0.570 | 0.975 | +0.8569 [+0.3766, +1.4123] * |
| `combined_long` | 4.44975 | 5.6049 | 0.570 | 0.949 | +0.4285 [+0.0260, +0.8525] * |
| `api_only` | 3.68384 | 4.8135 | 0.595 | 0.962 | -0.3374 [-0.5807, -0.1007] * |
| `api_rating` | 3.69803 | 4.7993 | 0.595 | 0.962 | -0.3233 [-0.5576, -0.0872] * |

CRPS by slice.

| Candidate | all | changed_club | low_history | high_history | role_FWD | role_MID | role_DEF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pooled_role` | 2.29131 | 1.79539 | 1.81673 | 2.60777 | 3.22650 | 3.00665 | 1.43885 |
| `recent_raw` | 1.94469 | 1.55669 | 1.68277 | 2.15916 | 2.93816 | 2.34066 | 1.35871 |
| `long_run` | 1.81459 | 1.44100 | 1.63367 | 2.01752 | 2.75477 | 2.18781 | 1.26783 |
| `recent_long` | 1.81549 | 1.44247 | 1.63241 | 2.01930 | 2.75167 | 2.19268 | 1.26753 |
| `long_plus_env` | 1.81370 | 1.43688 | 1.61908 | 2.01902 | 2.75039 | 2.18598 | 1.26916 |
| `context_share` | 1.81630 | 1.60822 | 1.63010 | 2.01329 | 2.78223 | 2.17730 | 1.26693 |
| `context_share_recent` | 1.81958 | 1.61671 | 1.62874 | 2.02136 | 2.78262 | 2.18745 | 1.26661 |
| `combined_long` | 1.96393 | 1.58989 | 1.71856 | 2.15812 | 2.97372 | 2.33926 | 1.39443 |
| `api_only` | 1.80692 | 1.33348 | 1.60517 | 2.00483 | 2.71099 | 2.16656 | 1.29137 |
| `api_rating` | 1.80542 | 1.33397 | 1.60533 | 2.00366 | 2.71828 | 2.15827 | 1.29240 |
| cases | 4920 | 109 | 614 | 1753 | 965 | 1841 | 1739 |

Persistence of the residual the mapping does not explain.

| Candidate | Players | Half-split correlation (95% CI) | Persistent sd | Noise sd |
| --- | ---: | --- | ---: | ---: |
| `pooled_role` | 464 | +0.624 [+0.553, +0.692] | 0.821 | 0.641 |
| `recent_raw` | 464 | +0.418 [+0.318, +0.518] | 0.556 | 0.658 |
| `long_run` | 464 | +0.301 [+0.192, +0.410] | 0.436 | 0.668 |
| `recent_long` | 464 | +0.296 [+0.186, +0.406] | 0.432 | 0.668 |
| `long_plus_env` | 464 | +0.308 [+0.198, +0.417] | 0.443 | 0.667 |
| `context_share` | 464 | +0.331 [+0.221, +0.438] | 0.468 | 0.667 |
| `context_share_recent` | 464 | +0.323 [+0.214, +0.430] | 0.459 | 0.668 |
| `combined_long` | 464 | +0.484 [+0.398, +0.571] | 0.624 | 0.648 |
| `api_only` | 464 | +0.342 [+0.236, +0.446] | 0.473 | 0.660 |
| `api_rating` | 464 | +0.336 [+0.230, +0.441] | 0.468 | 0.661 |

### The result that was not expected

On creation and on shot volume, the API count representation beats the Understat
process representation at predicting the process source's own marks.

| Comparison | Chronological | Across club changes |
| --- | --- | --- |
| `api_only` − `long_run`, shooting | +0.0042 [−0.0005, +0.0085] | +0.0259 [−0.0346, +0.1005] |
| `api_only` − `long_run`, creation | **−0.0046 [−0.0071, −0.0020]** | **−0.0366 [−0.0613, −0.0144]** |
| `api_only` − `long_run`, shot volume | −0.0077 [−0.0268, +0.0120] | **−0.3374 [−0.5807, −0.1008]** |

A representation built from goals, shots, shots on target, assists and key passes
predicts a player's future xA better than his own xA history does, both
chronologically and after a transfer. On shooting the two are indistinguishable.

The signal audit anticipates this. xA has a within-player-season split-half
reliability of 0.112, against 0.859 for total passes, 0.692 for assists and 0.665 for
shots on target. A noisier mark is a worse predictor of itself than a cleaner
correlated mark is, even when the noisier mark is the target.

Two things confound the comparison and neither is resolved here. The API family sees
appearances from 2016/17 while the process population starts in 2023/24, so it has
more history per player, which matters most for exactly the transfer episodes where
it wins by the most. And the API family carries more fields. A depth-matched variant
would separate these, and is recorded as follow-up.

## Named checks against the pre-registration

The [pre-registered checks](player_layer_prechecks.md) were recorded before any
candidate was fitted. They are falsification cases, never tuning targets, and no
hyperparameter was changed after looking at them.

| Case | Pre-registered expectation | Observed |
| --- | --- | --- |
| Erling Haaland | Shooting far above the forward population with narrow intervals, not dependent on being told Manchester City score a lot | Highest shooting estimate in the league under `long_run`, which contains no club term at all: 0.806 xG/90 at 2.07× the forward population, with the narrowest player-local uncertainty of any attacker (0.167). Under `api_only`, which never sees Understat, he is 2.18× on `api_long_shots` +0.65 and `api_long_goals` +0.33. Adding the club environment to the raw rate moves him by +0.058 in log space. |
| Mohamed Salah | Elevated on both components, with creation separated from shooting | 3.56× the midfield population on shooting and 2.03× on creation — elevated on both, by clearly different amounts |
| Bukayo Saka | Creation clearly above the population; shooting elevated but less than Haaland | Top of the creation table at 2.32× the midfield population, and separated from Haaland on creation by 2.38× [1.16, 4.87]. On shooting he is 0.362/90 against Haaland's 0.806, separated at 0.45× [0.24, 0.85]. |
| Dominic Solanke | Estimate survives the club move; not dominated by the new club | Carries across the Bournemouth-to-Tottenham move on his own evidence at 0.379/90, 0.98× the forward population, with 17 matches of retained process exposure behind it |
| Low-history control | Visibly wider intervals than an ever-present starter | Alex Tóth, 1.7 matches of process exposure: player-local uncertainty 0.715 against Haaland's 0.167 at 30.6 matches — more than four times wider |
| Team-context control | Context adjustment should move a strong-club player with an ordinary share down relative to raw rates | Behaves as expected directionally — Haaland's share-based estimate is below his raw-rate estimate — but the portability result below shows that this correction does not travel |
| Goalkeeper and centre-back | Attacking components near zero, carried by role pooling | Pickford 0.0012 xG/90 and Saliba 0.060, both near their role populations, with player-local uncertainty of 2.92 and 0.56 where there is little or no attacking evidence to shrink from |

The mapping uncertainty shared by all players is small; the player-local uncertainty
driven by a player's own exposure is one to two orders of magnitude larger. Merging
them into a single band would hide the only part that distinguishes players, which is
why the inspector reports them separately and compares players on the difference
rather than on overlapping marginal bands.

The pairwise diagnostic is honest about what it cannot resolve. On absolute shooting
rate, Haaland separates from Saka, Solanke, Mbeumo, Tóth, Saliba and Pickford, but
**not** from Isak (0.67× [0.37, 1.21]), Havertz or Salah. The elite tier is separated
from the rest; its members are not separated from each other at this evidence depth,
and the layer says so rather than implying an ordering the data will not carry.

One decomposition is worth naming. Under the rating ablation, `rating_long`
contributes **−0.156** to Haaland — the proprietary rating pulls the league's most
extreme shot generator *down* against the transparent shot and goal evidence.

## The questions this batch had to answer

| Question | Answer |
| --- | --- |
| Does the layer distinguish elite attacking specialists from ordinary players? | Yes. On shooting, a pooled role prior scores 0.396 CRPS against 0.327 for the player's own long-horizon rate, a gap of +0.070 [+0.055, +0.086]. Role-relative estimates separate the elite tier from the population with intervals on the difference, not on overlapping marginal bands. |
| Is the Haaland problem missing features, team attribution, or a symmetric scalar? | Neither missing features nor team attribution. It was the discovery mechanism plus a data semantics error. Reading provider nulls as zero, and estimating the player's own process directly rather than through club-centred lineup share, puts him first in the league at 2.07× the forward population on a representation with no club term, and at 2.18× on one that never sees Understat at all. |
| Does recent information help beyond long-run history? | Barely, and in the opposite direction to intuition. On shooting `recent_long` gains −0.0013 [−0.0023, −0.0004] over the long-run rate: statistically real, practically negligible. Its fitted coefficient is negative (−0.09) against a positive long-run coefficient (+0.62), so recent form enters as a mean-reversion correction rather than as extra signal. Recent rates used alone are much worse (+0.024). |
| Is recent information portable, or a second measurement of team form? | Largely the latter. Once the long-run rate is known, the target club's attacking environment gets a coefficient of only +0.05 and buys −0.0003 [−0.0013, +0.0008] in CRPS. The raw long-run rate already carries the club environment, and there is little separate portable recency. |
| Does context adjustment improve transferability? | No — it makes it worse. Across 79 club changes the share decomposition costs +0.069 [+0.025, +0.121] on shooting and +0.045 [+0.015, +0.077] on creation against the raw long-run rate. Handing the same candidate the club environment *without* the decomposition is neutral (+0.007, interval spanning zero), which localizes the failure to the decomposition rather than to the environment estimate. Recorded as a negative result. |
| Does the API rating contain incremental information? | No demonstrable increment. The matched ablation favours rating in five of six comparisons, but no interval excludes zero (shooting −0.0004 [−0.0021, +0.0013] chronologically, −0.0109 [−0.0356, +0.0097] across transfers). The transparent representation is not missing something the proprietary score supplies. |
| Does evidence depth produce meaningful uncertainty differences? | Yes. Player-local uncertainty scales with retained exposure — 0.167 for a player with 30.6 matches against 0.715 for one with 1.7 — and 90% interval coverage holds at 0.94 to 0.95 across the low- and high-history slices rather than collapsing on the thin one. |
| Are persistent player residuals identified? | Yes, and the diagnostic also shows how much the layer already absorbs. Splitting each player's scored cases chronologically in half, the pooled role prior leaves a half-to-half residual correlation of +0.608 — nearly all persistent player variation, since it models none of it. The long-horizon process rate cuts that to +0.254 and the persistent log-rate dispersion from 0.575 to 0.274. So the representation absorbs more than half of the identified player signal, and a real, measured remainder (interval +0.156 to +0.348, excluding zero) is still unextracted. |
| Is one scalar player value defensible yet? | No. The summed xG+xA mark predicts each component significantly worse than that component's own history: +0.018 [+0.014, +0.023] on shooting, +0.017 [+0.011, +0.023] on creation, +0.149 [+0.100, +0.201] on shot volume, and +0.068 [+0.028, +0.109] across transfers. The convention destroys information. |

## Limits of this evidence

Every score conditions on the exposure the player actually received. That is
deliberate — it isolates the process rate from lineup forecasting — but it means none
of these numbers is a deployable forecast, and a layer that predicts process well
could still fail once minutes must also be predicted.

The comparison between the process candidates and `api_only` is not a like-for-like
information comparison. API appearance evidence runs from 2016/17; the Understat
process population begins in 2023/24. The API-only family therefore sees more history
per player, particularly for the transfer episodes, where the frozen estimate depends
most on depth. The cases are identical; the evidence available to each representation
is not, and the comparison should be read as "which representation, given what it can
see" rather than "which signal is better".

There are 79 observed club changes with enough evidence on both sides. That is a
small sample for the portability question, and the player-clustered intervals reflect
it. The direction of the context-adjustment result is consistent across all three
marks, which is reassuring, but the magnitude is not well determined.

Club changes here are retrospective labels. The estimate is frozen before the
player's first appearance for the new club, which makes it cutoff-safe with respect
to that club's evidence, but it is not a claim that a transfer was known to any
forecaster at that date, and no announcement timing is asserted.

The mapping's parameter covariance treats cases as independent, which understates
mapping uncertainty given repeated players. The predictive distribution is dominated
by the empirical residual term, so the effect on the reported coverage is small, but
the mapping band in the inspector should be read as a lower bound.

Interval coverage is close to nominal and slightly conservative rather than
optimistic. This is an empirical assessment on retained data, not a calibration
guarantee for future seasons.

None of this establishes causal player value. The output is a portable predictive
estimate of player process, conditional on football context and on what these two
providers actually measure.

## Follow-up recorded, not done here

Re-capture the 30 current-season Understat match payloads with a current retrieval
time so the 2026/27 process records can link against the full player names that
arrived after them. It changes nothing in this batch's window.

Make `api_football.identity_keys` incremental. A transfers payload publishes team
rows, so the cache added here still invalidates on every transfers record and a full
replay spends most of its time rebuilding the store. Folding published rows into the
cached maps would remove the last slow path, but it must reproduce the view's
deduplication order exactly, which is why it was not attempted mid-batch.

Add a depth-matched variant of the API-only family restricted to the process window,
so that the process-versus-API comparison is not confounded by the API's deeper
history.

## Reproduction

```
python scripts/stage_player_process.py capture  --data data --manifest runs/research-ready-v1-player-gate-audit/manifest.json --stage runs/player-process-stage-v1
python scripts/stage_player_process.py publish  --data data --manifest runs/research-ready-v1-player-gate-audit/manifest.json --stage runs/player-process-stage-v1
epl-forecast data normalize --root data
python scripts/freeze_research.py --data data --output runs/research-ready-v2-player-layer/manifest.json
python scripts/audit_player_signals.py    --manifest runs/research-ready-v2-player-layer/manifest.json --output runs/player-signal-audit-v2
python scripts/audit_player_population.py --manifest runs/research-ready-v2-player-layer/manifest.json --output runs/player-population-audit-v2 --stage runs/player-process-stage-v1
python scripts/evaluate_player_layer.py   --manifest runs/research-ready-v2-player-layer/manifest.json --output runs/player-layer-v1 --marks xg xa process_shots --horizon-days 90
python scripts/inspect_player_layer.py    --manifest runs/research-ready-v2-player-layer/manifest.json --output runs/player-layer-inspect-v1 --cutoff 2026-06-01 --marks xg xa --players "Erling Haaland" ...
python scripts/preview_player_layer.py    --manifest runs/research-ready-v2-player-layer/manifest.json --evaluation runs/player-layer-v1 --output runs/player-layer-preview-v1/player_layer_preview.html --cutoff 2026-06-01
python scripts/report_player_layer.py     --run runs/player-layer-v1
```

`runs/player-layer-preview-v1/player_layer_preview.html` is a self-contained offline
inspector: component leaderboards with uncertainty, per-player feature decomposition
and evidence timelines, head-to-head differences, frozen pre-transfer estimates
against realized new-club process, and the evaluation tables.

## Decision

**Refine.** The core question is answered affirmatively, and three specific,
measured weaknesses stand between this layer and something an architecture should
consume.

What is settled. There is credible portable player information and it is large. A
representation reading only a player's own long-horizon attacking process, shrunk
toward his role population with explicit exposure, beats a pooled role prior by
+0.070 [+0.055, +0.086] CRPS chronologically on shooting and by +0.251 [+0.142,
+0.369] across 79 observed club changes. It survives a change of club. It recognizes
materially different attacking profiles — an elite shot generator, an elite creator,
and the difference between them, with intervals on the difference — using a
representation that contains no club term at all, so it cannot be discovering them
from team goals. Uncertainty separates a small shared mapping component from a large
player-local component that scales with retained exposure, and empirical interval
coverage is close to nominal and slightly conservative rather than optimistic.

Three weaknesses are identified, and each is specific enough to act on.

Persistent player residuals remain identified after fitting. The diagnostic is
readable because the pooled role prior anchors it: modelling no player information at
all leaves a half-to-half residual correlation of +0.608 and a persistent log-rate
dispersion of 0.575. The long-horizon process rate absorbs more than half of that,
down to +0.254 and 0.274 — but the remainder's interval, +0.156 to +0.348, excludes
zero. There is real, portable player information that none of these representations
extracts, and its size is now measured rather than guessed. That is the strongest
argument against treating the layer as finished.

The two data sources absorb different amounts of it. On shooting, the process
representation leaves +0.254 of residual player structure where the API count
representation leaves +0.316, so the Understat evidence is capturing more of what
persists about a shooter even where the two score alike. That is a reason to keep the
process source despite the creation result below, not to drop it.

The creation component is the weak one, and its own richer source is not the best
predictor of it. Understat xA has a within-player-season reliability of 0.112, and an
API count representation predicts future xA significantly better than xA history
does, both chronologically and after a transfer. Creation is not yet well
represented, and the fix is more likely to be a better creation *measure* than a
better creation *model*.

Context adjustment failed. Decomposing a player's rate into a portable share of his
club's attacking process times the new club's environment is significantly worse
after a transfer than the raw long-horizon rate, on every mark. Handing the same
candidate the club environment without the decomposition is neutral, which localizes
the failure to the decomposition itself. This should stay out, and should not be
rescued by raising player prior variance, weakening shrinkage or removing centring
and then judging success from a more plausible leaderboard.

Two further results should be treated as settled and not revisited. A single combined
attacking scalar is not defensible: the summed xG+xA mark predicts each component
significantly worse than that component's own history, everywhere. And the
proprietary rating contains no demonstrable incremental information over the
transparent counts, which is a good outcome — it means the transparent representation
is not missing something only a black box supplies.

What this does not settle, by construction: whether the layer helps a club or match
model; whether it survives having to predict minutes rather than condition on them;
and whether the Understat process evidence earns its cost over the transparent API
count representation, which on this evidence it does not clearly do outside shooting.
Those are the questions a later architecture should ask of this layer as an
independently understood input, rather than as another jointly fitted latent term
whose meaning depends on the surrounding club model.
