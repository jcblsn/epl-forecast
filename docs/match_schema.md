# Canonical data boundary

`src/epl_forecast/datasets.py` defines the durable canonical schema and query views.
Parquet is the persisted tabular format; DuckDB is an embedded query engine over
manifest-listed files. No persistent database service or compatibility CSV cache
is required. Report CSVs remain output artifacts, not the analytical data layer.

| Table | Grain |
| --- | --- |
| competition_seasons | Competition and season |
| teams | Canonical team and explicit provider ID |
| fixtures | Match, with regular/playoff stage and source fixture ID |
| players | Stable player identity and explicit provider IDs |
| memberships | Player/team/season and membership evidence basis |
| appearances | Match/player/team, nullable minutes and statistics |
| availability | Player, fixture/round/interval scope, captured state |
| transfers | Player, date and origin/destination |
| team_process | Match/team, distinct provider observations |
| player_process | Match and source player, nullable canonical mapping |
| odds | Match and quote family |

Each observation retains provider, actual retrieval time, evidence basis and raw
hash. `<table>_observations` exposes retained history; the base view selects the
latest row per provider and natural key. Complete-snapshot consumers must use
request scope and timestamp to recognize removals, including empty snapshots.
Missing a record never means the player was healthy or registered elsewhere.

Raw files live at `data/raw/<provider>/<content hash>.<extension>`. Successful
requests live in `data/requests/`; publication manifests in `data/manifests/`
list hashed Parquet files under `data/parquet/<table>/`, partitioned by competition
and season where applicable. Files without a publication manifest are invisible.

`Dataset(root, cutoff)` exposes only captures retrieved by the given timestamp.
`Dataset.fixtures()` reconciles providers and rejects contradictory identities,
finished dates and scores. `matches()`, `process()` and `player_history()` provide
model-ready records. Models do not interpret provider payloads.

Canonical regular-season fixture IDs use competition, season, home and away team;
postponement does not change identity. Playoff IDs are distinct. Player IDs are
anchored to stable API-Football IDs, never names. Transfers and multi-club seasons
remain multiple explicit membership records, not overwritten player attributes.

Historical research may use retrospectively retrieved outcomes with the explicit
next-day availability assumption. This differs from replay of truly captured
pre-match evidence; the latter always requires actual retrieval-time filtering.
