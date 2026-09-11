# Data inventory

The active migration plan is [data_architecture_migration.md](data_architecture_migration.md).
Provider payloads remain local and subject to provider licensing.

| Provider | Retained purpose | Important boundary |
| --- | --- | --- |
| API-Football | Fixtures, teams and league standings for all four divisions; current squads, players, transfers and injuries for all four; historical player appearances, sidelined records and per-match team statistics for the top two | Historical responses are retrospective; current squads cannot reconstruct historical registrations. League One and League Two player-level history is not backfilled. |
| football-data.co.uk | All four divisions' results, odds, shots and shots on target from 2010/11 | Historical odds have retrieval provenance, not invented pre-kickoff capture times. |
| Understat | PL team and player xG/process | No Championship, League One or League Two xG; team and player xG are distinct concepts. |
| FPL | PL availability, news, round playing probabilities | Current observations only; no historical player restoration or fixture dependency. |

API-Football fixture coverage begins in 2010 for PL and 2011 for Championship;
player-statistics coverage begins in 2014 and 2015 respectively, injuries in 2020.
Per-match team statistics arrive with fixture detail captures from 2016/17, and
carry the provider's own expected goals from 2022/23 in both leagues, which is the
only Championship xG in this archive. Standings are the provider's league table
including sanctions; they are the evidence behind realized final points, and the
retained snapshot for 2017/18 Championship is a partial mid-season table rather
than a final one. League One and League Two fixtures, teams and standings are
retained from 2015/16; their 2017/18 standings are also not final tables, and their
curtailed 2019/20 seasons have incomplete fixture lists. One API-Football fixture
record contradicted by the provider's own final standings is listed in
`src/epl_forecast/data/api_fixture_disputes.json`.
Endpoint flags describe advertised coverage, not verified completeness. The local
archive audit reports actual counts and gaps. Transfers and sidelined depth vary
by player. Stable API IDs anchor canonical player identity; explicit FPL and
Understat mappings do not depend on player names as keys.

`uv run epl-forecast data audit` verifies published hashes and fixture consistency,
then writes `data/audits/coverage.json`. Inspect season counts, missing appearance
coverage, incomplete starting lineups, unresolved mappings and uncaptured player
histories. Empty successful captures count as checkpoints, not proof of health.
Raw request manifests preserve enough evidence to investigate provider omissions.

Audit arithmetic is deliberately conservative, because a false ready is worse than
a false not-ready. A finished fixture counts as complete only when each of its two
teams has exactly eleven starters with usable identity and minutes, so a duplicated
identity on one side cannot offset a missing starter on the other. Uncaptured
transfer and sidelined histories are set differences between the canonical players
that need them and the API IDs with their own captured response, never a subtraction
of aggregate counts. Reported identity contradictions cover unapplied or chained
aliases, provider IDs shared by several canonical players, and same-team name
collisions inside one fixture.

The Pro plan provides 7,500 requests/day; the local backfill reserves 1,000 for
ongoing collection. Successful requests resume from immutable checkpoints.
Subscription and response quota headers are checked at runtime. No provider key
is stored in committed files, request URLs or canonical tables.
