# Data inventory

Audit begun 2026-09-05. This records source inspection before choosing model details.
The machine-readable [season audit](data_audit.csv) is generated from the pinned snapshot.

## Completed initial audit

The [season audit](data_audit.csv) covers 14,912 results: 6,080 PL and 8,832
Championship matches, 2010/11–2025/26, with 61 reviewed team aliases. All 32 files
have the expected teams and complete ordered home/away pair coverage. Core fields
have no missing values or contradictory results. There are 36,346 valid odds
triplets across the four retained families. Two Championship Bet365 triplets have
invalid values and are omitted from the odds table; their match results remain.
One Championship match in 2018/19 lacks all four shot counts. PL Bet365 coverage
is complete; market-average closing coverage is complete from 2019/20 onward.

Kickoff times are absent in all 18 files before 2019/20. The 2019/20 season extends
into July; the 2022/23 Championship starts in July. Parsing must not assume an
August-to-May season or order rows by an original matchweek label.

Scoring levels and home advantage vary by season. PL home/away goal covariance is
usually negative in the marginal season data; this does not establish conditional
dependence after accounting for team strength. It motivates later scoring checks,
not a decision to add a correlation parameter before backtesting.

The initial comparison therefore uses league frequencies, league goal rates, and
a regularized team attack/defense Poisson model. A 1,095-day window, 365-day goal
likelihood half-life and ridge strength 5 are explicit, unoptimized starting
settings in `configs/baselines.toml`. These are experiment parameters, not findings.

## Source decisions

| Source | Coverage and fields | Access / suitability | Initial decision |
| --- | --- | --- | --- |
| [Football-Data](https://football-data.co.uk/data.php) | Results advertised from 1993/94; men's English divisions include Premier League and Championship. Sampled 2010/11, 2014/15, 2019/20, 2024/25, 2025/26: 380 PL and 552 Championship results in every file; no missing dates, teams or full-time scores. | Public CSV downloads; no key. The bare hostname works; `www` returned HTTP 503. The publisher describes use for league match prediction; no general open-data redistribution license was found on the inspected pages. Keep downloads local and publish manifests and derived research. | Primary historical dataset. |
| [OpenFootball JSON](https://github.com/openfootball/football.json) | Public fixtures/results for PL and Championship; no odds or xG. CSV sister archive ends at 2020/21, so it is unsuitable as the sole recent source. | Public-domain project; no key. Generated JSON updates depend on manually maintained upstream results. Inspect season completeness before use. | Candidate independent cross-check / fixture source. |
| [StatsBomb open data](https://github.com/hudl/open-data) | The actual competition catalogue lists men's PL 2003/04 and 2015/16; this is not a continuous PL panel. Events, shots and lineups are available for selected competitions. | Public files; attribution requirements apply to published analysis. | Optional research, not a longitudinal PL backbone. |
| [Understat EPL 2014/15](https://understat.com/league/EPL/2014) | Historical EPL xG page exists; other listed leagues do not include Championship. Full match coverage, revisions and collection timestamps are not yet audited. | Public site; no documented, verified ingestion contract established in this audit. | Optional; do not assume completeness or use xG as a requirement. |
| [FBref / Sports Reference](https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/) | Publisher announced removal of advanced football data in January 2026. | Direct announcement returned 403 here; announcement text was available in the publisher's [category archive](https://www.sports-reference.com/blog/category/statgeekery/). [Bot policy](https://www.sports-reference.com/bot-traffic.html) also constrains automated access. | Do not build an xG dependency on previously available FBref fields. |
| [football-data.org](https://www.football-data.org/pricing) | Separate service with fixtures, tables and delayed scores on a free tier; deeper history is listed on paid plans. | The unauthenticated PL match endpoint returned 403. An account/API token is required to validate its match coverage. | No credentials needed for the historical milestone. Revisit only if a live fixture requirement warrants it. |

## Live collection

The September 5, 2026 capture added FPL
[players/availability](https://fantasy.premierleague.com/api/bootstrap-static/) and
[fixtures/results](https://fantasy.premierleague.com/api/fixtures/), plus
[Football-Data latest fixtures/odds](https://football-data.co.uk/fixtures.csv) and
current E0/E1 season files. All five downloaded without authentication. The FPL
2026/27 schedule had 380 fixtures and 28 full-time results, including eight marked
provisional; the PL CSV had 20 results, all agreeing with FPL. Raw snapshots retain
observation times and complete payloads even for fields not yet modeled.

The current season CSV also contains `HxG`/`AxG` columns. Their definitions and
historical coverage have not been audited; their presence does not establish a
usable longitudinal xG source. See [live collection and forecasts](live.md).

## Historical consistency and leakage

The sampled files' core result columns are stable. Header width changes from 68–71
to 106–132 columns. Kickoff time is absent in older samples and present from the
2019/20 sample. Use dates and next-day result availability, with all matches on a
date predicted before training on any of them. Retain source time text without
inventing a verified timezone or result-publication timestamp.

[Field notes](https://football-data.co.uk/notes.txt) distinguish scores, match
statistics and odds. Shots, cards, corners and half-time scores describe the match
being predicted: they must not enter its pre-match features. Raw retention permits
future lagged-feature experiments without putting those fields in model inputs.

Odds must remain an external comparison. The publisher distinguishes pre-closing
and closing prices from 2019/20; individual collection timestamps are unavailable.
It also warns that Pinnacle prices became stale in July 2025. Do not mix odds
families silently or label closing prices a same-horizon, start-of-day forecast.
[Source description](https://football-data.co.uk/data.php)

These are retrospectively retrieved records. Their hashes make local runs
reproducible; they do not prove that later corrections were visible historically.
The next-day availability rule is an explicit assumption for final scores, not a
record of publication. Future rest/congestion experiments need archived fixture
announcements rather than dates reconstructed after postponements.

## Initial sampling plan

Audit every PL and Championship season from 2010/11 through 2025/26 before modeling.
This offers multiple chronological evaluation seasons within the modern 20-team
PL format and retains lower-division continuity for later experiments. It does not
establish 2010 as the optimal history boundary. Championship results will initially
be normalized but not pooled into PL strength estimates without a division model.

Validate counts, unique ordered home/away pairs, team counts, score/result agreement,
dates, missingness and odds validity. Require complete season schedules for the
historical season simulation. Document point deductions separately: match results
alone cannot reconstruct an official table after sanctions.
