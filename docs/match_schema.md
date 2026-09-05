# Normalized match schema, version 1

`data normalize` writes deterministic UTF-8 CSV with LF newlines. Matches are
sorted by date and match ID; odds are sorted by match ID and family. Raw files are
never edited. `manifest.json` hashes every processed table and coverage report.

## matches.csv

| Field | Type | Meaning |
| --- | --- | --- |
| match_id | string | `competition:season:home:away`; ordered opponents uniquely identify a league fixture. |
| competition_id | string | `eng-premier-league` or `eng-championship`. |
| season_id | string | Start and end years, e.g. `2024-2025`. |
| match_date | ISO date | Recorded date of play; date precision is the evaluation clock. |
| home_team_id, away_team_id | strings | Reviewed aliases from the team registry, shared between divisions. |
| home_goals, away_goals | nonnegative integers | Completed full-time scores. Missing scores are errors, never zero-filled. |
| outcome | enum | `H`, `D`, `A`, checked against the score. |
| available_on | ISO date | Assumed first usable day: `match_date + 1 day`. |
| source_sha256 | hex string | Raw blob hash; joins to the source snapshot. |
| source_row | integer | Source CSV row number, counting the header as 1. |
| source_time | string or empty | Original kickoff time, retained without a verified timezone claim. |

The source snapshot contains source name, original URL, season, division, original
retrieval timestamp, byte size and SHA-256. Actual re-download times belong to raw
metadata sidecars and do not change normalized rows. The snapshot's original
retrieval time is not a historical result-availability timestamp.

Unknown team names, self-matches, duplicate ordered pairs, dates outside the
season, fractional/negative/missing goals and inconsistent outcome labels fail
normalization. July dates are valid. `coverage.json` records per-season expected
counts, actual counts, fields, missingness, odds validity and scoring summaries.
Incomplete seasons are identified; simulation requires a complete schedule.

## odds.csv

| Field | Meaning |
| --- | --- |
| match_id | Match foreign key. |
| family | Bet365 pre-closing, Betbrain average pre-closing, market average pre-closing, or market average closing. |
| home_odds, draw_odds, away_odds | Decimal prices, finite and strictly greater than 1. |
| source_columns | Exact original column triplet, separated by semicolons. |
| source_sha256, source_row | Raw provenance. |
| observed_at | Empty: the archive has no individual collection timestamp. |

A family is retained only when all three prices are valid. Invalid and missing
triplets are counted separately. Results are retained even when odds are unusable.
No fallback silently mixes bookmakers, market averages or collection horizons.
The [source notes](https://football-data.co.uk/notes.txt) define the original fields.

## In-memory forecasting boundary

`Match` holds a completed score and provenance. `Fixture` holds identity, date,
competition, season and opponents only. Models receive past `Match` objects in
`fit(matches, as_of)` and a label-free `Fixture` in `predict_match(fixture)`.
They return `Forecast(H/D/A probabilities, optional score distribution)`.

Post-match statistics remain in immutable raw files for later lagged-feature
experiments. They are absent from the initial forecasting interface. The current
models train on one competition; importing Championship rows does not silently
treat Championship and Premier League strengths as comparable.
