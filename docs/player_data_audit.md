# Player data feasibility audit

Audited September 6, 2026. A retrospective M6 research dataset is feasible now;
strict historical publication-time replay and complete past injury/roster states
are not yet established. No player model was built.

The normalized table contains 253,509 player-fixture rows over 3,800 fixtures,
2016/17–2025/26. Reproduce it from the pinned, checksum-verified sources with:

```bash
uv run python scripts/audit_players.py
uv run pytest tests/test_players.py
```

The script restores missing raw files from immutable commit URLs. Its outputs are
`data/processed/players/player_matches.csv.gz` and the committed
[machine-readable audit](player_data_audit.json). The dataset is local and ignored
by Git, consistent with the project's other processed data. Its SHA-256 is recorded
in the audit; the [source manifest](../configs/player_data_snapshot.json) pins all
36 source files to commit `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` of the
[FPL Historical Dataset](https://github.com/vaastav/Fantasy-Premier-League/tree/9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88).

| Season | Normalized rows | Minutes | Usable starts / xG fixtures |
| --- | ---: | --- | ---: |
| 2016/17 | 23,679 | Yes | 0 |
| 2017/18 | 22,467 | Yes | 0 |
| 2018/19 | 21,790 | Yes | 0 |
| 2019/20 | 22,501 | Yes | 0 |
| 2020/21 | 24,365 | Yes | 0 |
| 2021/22 | 25,447 | Yes | 0 |
| 2022/23 | 26,505 | Yes | 244 |
| 2023/24 | 29,725 | Yes | 380 |
| 2024/25 | 27,283 | Yes | 380 |
| 2025/26 | 29,747 | Yes | 380 |

Each season contains 380 distinct completed fixtures. Starts and xG in 2022/23
are all-zero placeholders for the first 136 fixtures, through November 6. Useful
values begin November 12, 2022. Those placeholders become missing values, not
observed zero starts/xG. The remaining 244 fixtures and every fixture in the next
three seasons have exactly eleven reported starters per club. Earlier starts
cannot be recovered reliably from minutes alone.

All 3,800 canonical match IDs and dates also agree with the project's separately
sourced Football-Data match table. The normalized `season_id` uses the project's
`YYYY-YYYY` convention; `source_season_id` retains the archive's shorter label.

## Time and identity

Player identity uses `(season_id, fpl_element_id)`; element IDs are extensively
reassigned between seasons. The archived player `code` is complete and unique
within each audited season, and hundreds of codes recur across years. It is a
promising cross-season link, not a separately verified universal identity
guarantee. The season key remains authoritative; names are labels only.

Fixture clubs come from `was_home` and the opponent IDs recorded on both sides of
the fixture. These mappings agree with the independent `fixtures.csv` within the
same source archive for 2018/19 onward; 2016/17–2017/18 lack that file. Club names
map through season-specific team lists and the project's canonical registry.
Using final `players_raw.csv.team` instead would misassign 2,466 rows. Observed
multi-club players number 4–32 per season, demonstrating within-season transfer
coverage without projecting a final club backward.

The table excludes 59 postponed/unplayed placeholders in 2019/20, ten identical
duplicates in 2025/26, and 322 assistant-manager rows in 2024/25. Conflicting
completed duplicates fail normalization. Legacy 2016/17–2018/19 CSVs use Latin-1.

`expected_minutes_prior5` is a simple feasibility baseline: mean minutes across
the player's last five recorded fixtures on strictly earlier UTC dates, including
zero-minute rows. It resets each season and is missing for a debut without prior
history. Counts and the latest contributing kickoff are supplied. Tests show
that changing the target or appending future observations cannot change the
target feature, and same-day results are excluded. The target fixture's actual
minutes, starts, xG, and actual club assignment are outcomes, not pre-match inputs.

This establishes chronological feature construction, not exact historical data
availability. The archive was downloaded retrospectively and may include revised
statistics. `historical_observed_at` is deliberately empty; kickoff is never
substituted for publication time. Commit pinning freezes this audit's input but
does not prove what a forecaster saw before an old match. A strict replay needs
earlier source revisions or timestamped captures before each forecast cutoff.

## Observations and squads

Goals, FPL-defined assists, concessions, clean sheets, saves, penalties and cards
are available per fixture throughout. These are provider-defined observations,
not interchangeable with other providers' event definitions. xG, xA, expected
goal involvement and xG conceded become useful in November 2022. Historical
2016/17–2018/19 files also have nonzero passing, chance-creation, tackling,
recoveries and clearance/block/interception fields; these disappear in 2019/20.
Tackles, recoveries and clearance/block/interception observations return in
2025/26 with `defensive_contribution`. Missing fields stay missing. The JSON audit
records both nonempty and nonzero counts to expose schema-only availability.

Fixture histories reconstruct appearances and observed club changes around
transfer windows. They cannot establish exact signing dates, eligible unused
players absent from the archive, full matchday benches, or who was known injured
before a match. Zero minutes does not identify the reason for absence. Past
appearances must not be combined with future roster membership to create a
historical expected lineup. M6 needs a cutoff-specific candidate squad and
expected-lineup uncertainty in addition to the prior-minutes baseline.

The two September 5 and one September 6, 2026 local FPL bootstrap captures
contain 653 players each. The two September 5 responses have identical bytes. Each has status for all players, news for 172, `news_added` for
232, next-round playing probability for 232, and this-round probability for
230. They also contain selection/transaction/removal flags, squad team IDs,
birth dates, team join dates, and some scout risk/news fields. These snapshots
are genuinely usable only from their recorded collection timestamps onward;
`news_added` does not reconstruct earlier versions of a news item. They hold
cumulative player statistics, not fixture-level player histories. There is no
local historical injury series.

Final historical `players_raw.csv` files also expose availability fields, but
only at the source's captured state; projecting them backward leaks information.
Birth/join-date columns exist in 2024/25 onward, and scout fields in 2025/26, so
they are not exclusively current capabilities. The upstream maintainer now
describes three updates per season after 2024/25, rather than weekly snapshots,
and explicitly warns about potential lookahead in `xP`; this table excludes
`xP`, FPL price, and fantasy points as modeling inputs.
[Upstream collection policy and leakage note](https://github.com/vaastav/Fantasy-Premier-League#notice).

M6 can begin with 2023/24–2025/26 for complete starts/xG and earlier seasons for
minutes/outcome priors. Before making point-in-time historical squad claims,
establish timestamped roster/availability reconstruction and audit code-based
identity links. Continue current captures; add player fixture histories when
implementing the M6 ingestion stage.
