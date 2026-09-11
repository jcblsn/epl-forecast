# Local collection and forecasts

All four divisions — the Premier League, Championship, League One and League Two —
use the same local collector and canonical data boundary. Run
`uv run epl-forecast data collect`, then `uv run epl-forecast forecast --competition
eng-premier-league` or the equivalent `eng-championship`, `eng-league-one` or
`eng-league-two` command. The EFL baseline configuration is `configs/championship.toml`.

API-Football credentials belong in the environment or ignored `.env`. Collection
preserves successful responses when another source fails and reports partial status
in `data/audits/collection.json`. Request records contain URLs, retrieval times,
raw hashes and observation context. Raw bytes are immutable and content-deduplicated.
Parquet publication is visible only after its manifest is written. A local writer
lock prevents concurrent ingestion; models query published files without a server.

## Recurring prospective capture

The local collection and forecast jobs, plus optional historical backfill, are installed with:

```sh
uv run python scripts/capture_prospective.py --install-launch-agent --backfill-requests 200
```

The collector wakes every twelve hours and captures due provider observations. The
separate forecast worker checks for canonical information changes or a twelve-hour
heartbeat. Expensive model runs therefore do not delay capture. M2 and M7 run for
every division; the player and process research models M5, M6 and M8 run for the
Premier League and Championship, where their inputs exist. Research model outputs do
not establish model promotion.
Each attempt records independent command outcomes and logs; failed forecasts are
retried on a later tick. All models in an attempt use one cutoff after collection.
M7 forecast archives publish structural probabilities and a separately labeled
market-assisted probability when an average pre-closing quote was captured by that
cutoff. The quote, de-vigged probabilities and retrieval timestamp remain in the
forecast JSON. Season simulation and exact-score matrices remain structural.
`--backfill-requests 200` installs a separate hourly job for bounded archive passes.
The API quota reserve protects current collection. Remove this option when the
historical archive is complete. Logs live under `runs/prospective/`.

`--collect-only` and `--forecast-only` run the workers independently. For a combined
manual run, omit `--install-launch-agent`; use `--force --simulations 20` for
a small operational smoke check. Installation should follow a successful manual
run. The active migration plan records whether this cutover has been verified.

## Sanctions in the live product

Collection refreshes the provider's league table alongside fixtures. A club whose
standings points differ from the points its archived results imply carries a
sanction, and a live capture is contemporaneous evidence that the sanction was in
force when the table was published, so current forecasts apply it to both the
current table and the projection. Retrospective backfills say only when this archive
learned of a sanction and never date one. Reviewed announcement dates, where a
registry has them, take precedence over either.

`scripts/verify_forecast_product.py` re-checks a published archive against the MVP
contract, including that the sanctions in force at the cutoff were applied and that
the Championship bracket used each simulated path's own latent states.

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

## Rebuild normalization

Stop the collection, forecast and backfill launch agents and finish active forecasts before running
`uv run epl-forecast data normalize`. This offline operation verifies raw hashes,
replays provider dependencies into temporary Parquet, validates the result, then
replaces the old normalized directories. It preserves requests and raw responses.
A failed replay leaves the old publication intact. The final directory replacement
requires no concurrent readers; restart collection afterwards. This is a rebuild,
not a second supported cache or a historical-observation timestamp rewrite.

During model development, scheduled collection and forecast checks run every twelve
hours. Fixture inventories and fixture details use a twelve-hour minimum refresh
interval, with no rapid match-day override. This deliberately trades late lineup
and availability coverage for a quieter archive. Raw timestamps still describe
actual captures; missing observations are never reconstructed later.

Do not raise the cadence merely because more frequent capture is possible. Raise
it before evaluating a model whose claimed advantage depends on late injury news
or confirmed lineups, because at twelve hours the archive cannot observe those
signals and the experiment could not detect the advantage it claims.

## Recent data first

Backfill prioritizes both leagues' current-season inputs and current-player histories,
then the preceding three seasons, before older coverage. It interleaves the leagues'
player requests. `data/audits/recent_readiness.json` separates usable recent inputs
from whole-archive completeness; complete historical backfill is not a prerequisite
for starting model work. Coverage readiness is distinct from model validation and
from historical point-in-time evidence.

Player readiness requires eleven starters with usable identity and minutes for each
team in every finished regular fixture of the window, and no audited identity
contradiction inside it. The report names the fixtures that fail, so remaining gaps
can be traced to a provider payload rather than inferred from a total.
