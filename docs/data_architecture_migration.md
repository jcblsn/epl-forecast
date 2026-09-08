# Data architecture migration

Status: implementation in progress. Accepted September 8, 2026.

## Objective

Replace snapshot/restoration and normalized CSV pathways with thin provider ingestion,
immutable raw captures, canonical Parquet, and embedded DuckDB queries. Support PL and
Championship ingestion, match forecasts and regular-season projections; preserve model mathematics, leakage discipline and prospective evidence.
No backward compatibility is required. Git restores code, not ignored local evidence.

## Decisions

- Football-Data: results, four existing odds families, shots and shots on target.
- API-Football: fixture schedule/status, stable player identity, lineups, appearances,
  statistics, current squads, transfers, injuries and sidelined periods.
- Understat: sole xG source, including player process observations; team match xG and
  additive player xG remain distinct. Championship xG is unavailable.
- FPL: only captured availability/news and playing probabilities with identity and round
  context. Delete historical restoration, element-summary and fixture ingestion.
- Delete OpenFootball and all old processed-data restoration and compatibility paths.
- API-Football IDs anchor opaque canonical player keys. Provider mappings are explicit;
  names only suggest links, never identify players. Ambiguous links are audited.
- No Reep runtime dependency: relevant namespaces exist, but the current downloadable
  release could not be inspected (403), so mapping coverage was not demonstrated.
- Retain original local snapshots and forecast runs as evidence; import observations with
  original retrieval timestamps. Do not maintain their old loaders.

## Canonical data and storage

Tables: competition_seasons, teams, fixtures, players, memberships, appearances,
availability, transfers, team_process, player_process, odds. Preserve nullable statistics,
source IDs, actual retrieval times, raw hashes, and retrospective/prospective evidence basis.
Current squad snapshots are not historical registration intervals. FPL probability scope
is a round, not a fabricated injury recovery date. Missing records do not imply health.

Raw content lives under data/raw/<provider>/<hash>.<extension>. Canonical Parquet lives
under data/parquet/<table>/ with competition/season partitions. Request checkpoints are
small JSON records; completed publication manifests list immutable Parquet files and hashes.
DuckDB queries only published files. One local writer lock protects collection/publication.
Strict replay filters by actual retrieval time; historical research uses an explicitly
labeled next-day outcome assumption. Historical records never get invented observation times.

Models, lineup construction and research consume canonical query results, never provider
payloads. Preserve existing regular-season fixture keys through postponements. Championship
playoffs get distinct IDs and are excluded from regular-season training and simulation.

## Backfill

API catalogue: PL fixtures/lineups from 2010, Championship from 2011; player match stats
from 2014/2015 respectively; injuries from 2020 in both. Coverage flags are not proof of
completeness. Current squads have no historical season parameter. Transfers/sidelined
histories have player-specific depth.

Verify Pro before backfill. Enumerate both league inventories, every player-season page,
and bundled fixture details (up to 20 IDs). Fetch transfers and sidelined once per unique
player and injuries per covered season. Expand Understat beyond the 36-match player sample.
Reuse valid local Football-Data/Understat raw captures. Checkpoint every request/page and
resume without refetching it. Reserve 1,000 of 7,500 daily requests for ongoing collection;
pace below 4 requests/second and response minute limits. Direct quota resets at midnight UTC.
Stop on entitlement errors; bounded retries for transient errors; resumable quota exits.
Audit expected fixtures, stages, starter counts, player coverage, pagination, identity links,
missingness and contradictory results. No inferred minutes for early missing statistics.

## Ongoing collection

Twelve-hour collection and forecast checks during model development, following the
user's September 8 steering. Fixture inventories and details have a twelve-hour
minimum refresh interval and no rapid match-day override. Squads refresh daily,
current player profiles weekly, and other due sources refresh at scheduled collection.
Final fixture details retain bounded completion/next-day/seven-day correction checkpoints.
Understat and Football-Data update as available; current transfers update daily in
transfer windows and weekly otherwise. Keep successful capture timestamps while
deduplicating raw content. Secrets use ignored .env or environment.

The slower schedule deliberately misses some late lineups and availability changes;
raise cadence only when the modeling work warrants the archive volume. A separate
local backfill job can consume its bounded quota without triggering new live captures.

## Implementation checklist

- [x] Canonical schemas, DuckDB queries, immutable publication, API preflight.
- [x] Ongoing collection and resumable backfill; import existing evidence once.
- [x] Forecasting, evaluation, lineup and research consumers migrated.
- [x] Installed collector replaced and scheduled execution verified.
- [x] Old adapters, restoration commands, outputs/configuration and obsolete tests removed.
- [ ] Historical archive audited; offline research verified.

## Acceptance and retirement

Validate 380/552 regular-season fixtures, playoff separation, eleven starters when complete,
nullable missing minutes, cross-season identity/transfers, contradictions and hashes.
Test pagination, HTTP-200 API errors, quota/retries, interrupted publication, idempotence,
complete empty snapshots versus failure, and actual cutoff handling. Future and same-day
outcomes cannot change earlier features. Preserve numerical-model tests and identical-input
predictions; document M6 data coverage changes. Run uv run ruff check . and pytest.

Keep this file active until every checklist item is complete. Then move it to
.archive/data_architecture_migration.md and remove its README link. Local historical
research must work without API access. Raw provider data stays local, subject to provider terms.

## Evidence

- https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide
- https://www.api-football.com/terms
- https://duckdb.org/docs/current/data/parquet/overview
- Authenticated probes: 380 PL / 557 Championship fixtures for 2023; both injury endpoints
  populated, Championship player statistics paginated over 59 pages. Single fixture details
  include events, lineups and player statistics. Supplied key initially Free; user subsequently
  confirmed Pro activation. Current FPL capture has 232 next-round playing probabilities.

## Steering during implementation

Both leagues are first-class, including match forecasts and 24-team Championship season
projections. Report automatic promotion and season-specific playoff qualification rather
than PL European-position columns. Championship playoff qualification expands from places
3–6 to 3–8 in 2026/27. Retain playoff fixtures separately; knockout advancement requires an
explicit extra-time/penalty observation model and is not implied by qualification probability.
Current project descriptions must not frame provider data as free or freely redistributable.
Source: https://www.efl.com/news/2026/march/05/efl-statement--sky-bet-championship-play-off-format/

## Implementation checkpoint: September 8

Canonical consumers and both-league season simulation are implemented. The rewrite
removed over 3,000 lines overall at the consumer-cutover checkpoint. The test suite
now contains 174 passing tests, including cutoff isolation, immutable publication,
fixture-scoped absence, empty squad replacement and bounded final-match refreshes.
M2 through M8 (excluding the retired M4 scheduling slot) are being smoke-tested for
both leagues before launch-agent installation. A current collection pass succeeded.

The initial 1,200-request resumed API pass paused at its invocation budget. An audit
found 5,799 players and 352,859 appearance records; historical transfers, sidelined
records and full Understat player coverage were still pending. Counts are checkpoints,
not completeness claims; `data/audits/coverage.json` is the current local authority.
The plan remains active until the archive and scheduled cutover are verified.

Remaining implementation checks include full raw replay/rebuild determinism, current
identity mapping coverage, obsolete source-configuration retirement, and final
collector verification. Historical backfill remains resumable and quota-limited.

Full offline replay of 1,685 raw requests passed after exposing two invalid historic
shot pairs, which are now explicitly unknown with audited raw evidence. The obsolete
processed CSV cache was removed; original raw data, snapshots and runs were retained.
The retired importer and source configurations are in `.archive/legacy_data/`.
All ten manual forecast checks passed (five models for each league). Collection and
forecasting now run as separate local scheduled jobs so model runtime cannot postpone
prospective captures. The suite currently contains 178 passing tests.

## Latest steering and current priority

Live collection and forecast checks are installed at twelve-hour intervals. The
separate historical job runs hourly with a 200-request budget and a daily quota
reserve; this does not create frequent live fixture snapshots.

API backfill now completes the current season for both leagues, then prioritizes
current-player sidelined and transfer histories, then the preceding three seasons
and their player histories, before older seasons. Player requests interleave the
two leagues. `data/audits/recent_readiness.json` reports the 2023/24–2026/27 input
window independently of whole-archive completion.

The recent fixture/results window is complete for both leagues. Initial starter-minute
coverage was complete for PL, but Championship had 82 affected matches across the
four seasons. Inspection found multiple provider IDs for the same player in lineups
and statistics, and zero IDs used as missing-ID sentinels. Fifty explicit API aliases
are recorded in `src/epl_forecast/data/api_player_aliases.csv`, with same-fixture
team/shirt-number evidence and raw hashes. These are deterministic provider identity
corrections, not names used as player keys. Full replay and readiness verification
of this repair remain in progress at this checkpoint.
