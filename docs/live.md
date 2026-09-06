# Live capture and forecasts

`data snapshot --season-start 2026` captures these public responses into a new
UTC timestamp directory under `snapshots/`:

| File | Source |
| --- | --- |
| `fpl_bootstrap.json` | [FPL teams, players and availability](https://fantasy.premierleague.com/api/bootstrap-static/) |
| `fpl_fixtures.json` | [FPL schedule, statuses and scores](https://fantasy.premierleague.com/api/fixtures/) |
| `football_data_fixtures.csv` | [Football-Data latest fixtures and odds](https://football-data.co.uk/fixtures.csv) |
| `football_data_E0.csv` | [2026/27 PL results and odds](https://football-data.co.uk/mmz4281/2627/E0.csv) |
| `football_data_E1.csv` | [2026/27 Championship results and odds](https://football-data.co.uk/mmz4281/2627/E1.csv) |

The manifest records per-response retrieval times, URLs, headers, sizes and hashes.
A failed source is recorded and the command exits nonzero after preserving the
successful captures. The bare Football-Data hostname worked on September 5;
`www` returned 503. Player and odds payloads are collected now for later use; they
do not enter M2 or M4 fitting. M4 currently uses completed historical Championship
seasons for promotion priors; partial current E1 captures remain archived for later use.

## Refresh

Run capture, then pass its printed directory to `forecast --snapshot <directory>`.
Each forecast gets a new directory in `runs/forecasts/`; `--output` can supply an
explicit empty directory. Open `index.html` locally. No server, external
publication or scheduler is required. Re-run after results or fixture changes;
capture regularly even when not changing the model. Back up `snapshots/` and
`runs/forecasts/`, which are ignored by Git.

M2 is the default. Use `--config configs/dynamic.toml
--model M4-dynamic-hierarchical-v1` for the M4 prototype. Its exports add attack
and defense SDs, their covariance, the entry prior and current PL appearance count.
Match probabilities integrate state uncertainty; each simulated season uses one
shared posterior draw. The page identifies the model and uncertainty treatment.

Fresh FPL data is required within 24 hours by default. Increase
`--max-snapshot-age-hours` explicitly for offline replay. The actual generation
and archival timestamps always remain current; replay does not backdate them.
Capture age does not prove upstream freshness: statuses and fixture times are
checked too, and the page shows the observed state time.

## Time and result handling

FPL kickoff timestamps are converted to London dates for fitting, matching the
historical date convention. Both models see only prior-date results. The season table fixes
all full-time results in the captured response, including same-day games. These
are different information boundaries, recorded as `model_results_cutoff` and
`state_observed_at`.

FPL can leave `finished=false` after full time while `finished_provisional=true`
and `minutes=90`. Those scores are usable, explicitly labeled provisional, and
may be corrected in a later snapshot. Current Football-Data results are checked
against FPL by canonical fixture ID, date and score; conflicts stop the forecast.
FPL can supply results that the CSV has not published yet.

The adapter checks the requested season, 20 canonical teams, all 380 ordered pairs,
unique source IDs, completion flags and observation times. Undated/postponed
fixtures retain their identities and null/old source kickoff values in exports.
Both current simulators hold states fixed within a path and can use a placeholder date. No
fixture date is invented for display or forward scoring. A model with rest or
future state evolution will need explicit schedule uncertainty.

In-progress or overdue fixtures suspend the season projection. Other match
forecasts and raw snapshots remain available; this is not an in-play model.

## Forward record

`archive.json` is written after the output files and records their hashes, the
actual archive time and fixtures whose captured kickoff was still in the future.
The command refuses to overwrite an existing run. Only completed archives count
as forward evidence. Check later rescheduling information when scoring, and choose
one consistent horizon per match, such as the last available archive at least
24 hours before kickoff. Do not select archived runs after seeing their accuracy.

Raw source observations and local timestamps are useful point-in-time evidence,
not a third-party publication timestamp or a reconstruction of past source states.

## First live run

On 2026-09-05 at about 19:58 UTC, all five responses were captured. The FPL schedule
contained 380 fixtures and 28 full-time results; Football-Data covered 20 of those
results and all agreed. The forecast fixed all 28 scores, fit M2 on 1,122 prior-date
PL results through September 4, and simulated the remaining 352 fixtures 10,000
times. All 352 match predictions were archived before their captured kickoff.

The initial raw snapshot is `snapshots/2026-09-05T195837.485290Z/`; the forecast is
`runs/forecasts/2026-09-05T200608.145383Z/`. These are local artifacts. Hull's roughly
61 expected points expose the league-average promotion prior's limitations; this
is a reason to prioritize Championship continuity, not a reliable claim that a
newly promoted club has become a top-four side.

The M4 comparison archive, `runs/forecasts/m4-2026-09-05/`, uses the same snapshot
and 10,000 posterior paths. Hull projects to 39.1 points with 36.0% relegation
probability. The [batch report](experiments/m4_dynamic.md) compares all promoted
clubs and separates model changes from uncertainty propagation. This is a more
plausible starting point, not evidence that the projection is accurate; historical
early-season performance still needs improvement.
