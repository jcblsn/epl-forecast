# Data inventory

The active migration plan is [data_architecture_migration.md](data_architecture_migration.md).
Provider payloads remain local and subject to provider licensing.

| Provider | Retained purpose | Important boundary |
| --- | --- | --- |
| API-Football | Both leagues' fixtures, players, squads, appearances, transfers, injuries and sidelined records | Historical responses are retrospective; current squads cannot reconstruct historical registrations. |
| football-data.co.uk | Both leagues' results, odds, shots and shots on target | Historical odds have retrieval provenance, not invented pre-kickoff capture times. |
| Understat | PL team and player xG/process | No Championship xG; team and player xG are distinct concepts. |
| FPL | PL availability, news, round playing probabilities | Current observations only; no historical player restoration or fixture dependency. |

API-Football fixture coverage begins in 2010 for PL and 2011 for Championship;
player-statistics coverage begins in 2014 and 2015 respectively, injuries in 2020.
Endpoint flags describe advertised coverage, not verified completeness. The local
archive audit reports actual counts and gaps. Transfers and sidelined depth vary
by player. Stable API IDs anchor canonical player identity; explicit FPL and
Understat mappings do not depend on player names as keys.

`uv run epl-forecast data audit` verifies published hashes and fixture consistency,
then writes `data/audits/coverage.json`. Inspect season counts, missing appearance
coverage, incomplete starting lineups, unresolved mappings and uncaptured player
histories. Empty successful captures count as checkpoints, not proof of health.
Raw request manifests preserve enough evidence to investigate provider omissions.

The Pro plan provides 7,500 requests/day; the local backfill reserves 1,000 for
ongoing collection. Successful requests resume from immutable checkpoints.
Subscription and response quota headers are checked at runtime. No provider key
is stored in committed files, request URLs or canonical tables.
