# Local collection and forecasts

Both the Premier League and Championship use the same local collector and canonical
data boundary. Run `uv run epl-forecast data collect`, then `uv run epl-forecast forecast
--competition eng-premier-league` or the equivalent `eng-championship` command.
The Championship baseline configuration is `configs/championship.toml`.

API-Football credentials belong in the environment or ignored `.env`. Collection
preserves successful responses when another source fails and reports partial status
in `data/audits/collection.json`. Request records contain URLs, retrieval times,
raw hashes and observation context. Raw bytes are immutable and content-deduplicated.
Parquet publication is visible only after its manifest is written. A local writer
lock prevents concurrent ingestion; models query published files without a server.

## Recurring prospective capture

The local macOS launch agent is installed with:

```sh
uv run python scripts/capture_prospective.py --install-launch-agent --backfill-requests 200
```

It wakes every ten minutes, collects due provider observations, and archives forecasts
when canonical information changes or a six-hour heartbeat is due. M2, M5, M6, M7
and M8 run for both leagues. Research model outputs do not establish model promotion.
Each attempt records independent command outcomes and logs; failed forecasts are
retried on a later tick. All models in an attempt use one cutoff after collection.
`--backfill-requests 200` enables a bounded resumable archive pass after forecasting.
The API quota reserve protects current collection. Remove this option when the
historical archive is complete. Logs live under `runs/prospective/`.

For a manual run, omit `--install-launch-agent`; use `--force --simulations 20` for
a small operational smoke check. Installation should follow a successful manual
run. The active migration plan records whether this cutover has been verified.

## Observation boundaries

`--cutoff` filters by actual provider retrieval time. Historical backfills are
retrospective evidence, not fabricated historical snapshots. Training additionally
excludes outcomes from the forecast's London calendar date. The season projection
fixes all captured completed scores, including today's scores. Games in progress,
awaiting results or with unresolved scheduling withhold the full projection.

Fixture-inventory freshness defaults to 24 hours. `--max-snapshot-age-hours` is the
current CLI spelling of the age limit and can be increased explicitly for offline
replay. Generated and archived timestamps remain actual timestamps.

FPL contributes only availability/news and playing probabilities for PL players.
The player model's optional 28-day probability recovery is a scenario assumption.
Unknown player position, missing minutes and unresolved identity remain explicit.
Championship does not receive invented FPL availability or Understat xG.

Championship simulation uses 24 teams, two automatic-promotion places and the
season's playoff-qualification places. Playoff fixtures have separate IDs and do
not enter the 552-match regular-season table. Qualification is distinct from
winning the playoffs. PL European qualification requires an explicit cup scenario.

Back up `data/` and `runs/`; they contain evidence that Git does not restore.
Legacy `snapshots/` remain local evidence from the retired collector.
