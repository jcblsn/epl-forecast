# Feasibility: expanding scope to League One and League Two

Lean desk study, not an implementation plan. Question: can the product's scope
grow from the Premier League and Championship (the current
[north star](../../north_star.md)) to all four professional English tiers — add
EFL League One and League Two? Are there any blockers that rule it out? This
does not size the work; it only checks whether anything stops it.

## Answer

No hard blocker. The product already runs a two-division version of every
mechanism a third and fourth division need: a goals source, a rules engine, a
promotion/relegation bridge, and a publication boundary that is generic by key,
not by competition. Adding League One and League Two is additive engineering
and — the larger cost — new empirical calibration work, not a redesign.

The one real gap (Understat xG) is already a gap at the Championship today and
the architecture already tolerates it there, so extending downward adds no new
kind of problem, just more of the same one.

## Data sources, checked per provider

- **football-data.co.uk (goals, results, odds).** `src/epl_forecast/data/sources.py`
  hardcodes `COMPETITIONS = {"E0": premier-league, "E1": championship}` and builds
  the fetch URL from that map. The site publishes the same CSV shape for `E2`
  (League One) and `E3` (League Two) back through the historical archive, same
  URL scheme (`mmz4281/<season code>/<div>.csv`). Adding two dict entries and two
  division codes is the entire change on this source. Per [CLAUDE.md](../../../CLAUDE.md),
  this must go through `capture.py`, not a reader tool — unchanged either way.

- **Understat (xG).** Confirmed by search: Understat covers exactly six leagues
  (EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL) — no English second tier or
  below, ever. This is not new information for this codebase: [cross_division.md](../cross_division.md)
  already measured it directly — 0 of 8,898 Championship matches have Understat
  coverage. M7 is already the frozen structural model "for both leagues" with
  "no evidence" from the Understat channel in the Championship
  ([mvp.md](../../mvp.md)). League One and League Two matches would be goals-only
  for the same reason Championship matches already are. No new failure mode, no
  new code path — just zero coverage two tiers further down instead of one.

- **API-Football (fixtures, lineups, injuries).** `LEAGUES = {39: premier-league,
  40: championship}` in `data/api_football.py`. League One and League Two are
  present in API-Football's coverage (confirmed by search); the exact league IDs
  are a cheap lookup against their own `/leagues` endpoint rather than a research
  question. The existing capture code already requires a paid tier
  (`status["requests"]["limit_day"] < 7500` gates ingestion — free tier is only
  100/day). Doubling the tracked clubs and fixtures roughly triples daily
  polling volume for lineups/injuries; current pricing tiers scale from 7,500 to
  75,000+ requests/day for a modest monthly cost, so this is a budget line, not
  a blocker.

- **FPL (`fantasy.premierleague.com`).** Explicitly "FPL's narrow prospective
  availability signal" and already Premier-League-only — the Championship
  product already ships without it. No new gap from adding lower tiers.

## Team identity registry

`src/epl_forecast/data/teams.csv` (63 clubs) is the reviewed source-name-to-slug
registry CLAUDE.md requires extending rather than reinventing. League One and
League Two add on the order of 40-50 more clubs (accounting for overlap with
clubs that already cycle through the Championship boundary). This is bounded,
mechanical review work, not a design problem — the same process already used to
grow this file from Premier-League-only to its current 63 rows.

## Competition rules

`data/rules.py` has a two-branch `league_rules()`: Premier League (head-to-head
tiebreak) and Championship (`automatic_promotion=2`, playoff bracket). League
One and League Two use the same EFL promotion/playoff shape as the Championship
branch already encodes (2 automatic promotion spots, 3rd-6th playoff), so this
is two more `if` branches with known parameters, not new rule design. The one
edge this introduces: League Two relegation feeds the National League, a tier
this product would not model — the same kind of boundary that already exists
today at League One (Championship relegation feeds a division this product
doesn't model), so it is a known pattern, not a new one.

## Promotion/relegation modeling — the real cost

This is where the work actually is, and it is real. `models/promotion.py`
hardcodes one boundary: module-level `PL`/`CHAMPIONSHIP` constants, and a
`DivisionBridge` base class with `PromotionBridge`/`RelegationBridge`
subclasses for exactly that pair. Going to four tiers means three boundaries
(PL↔Championship, Championship↔League One, League One↔League Two), and each
boundary is not just a code path — the Championship boundary alone required
several dedicated calibration studies to get right: `docs/experiments/entry_prior/`,
`relegation_entry/`, `playoff_conditioning/`, and `season_scoring_championship/`
all exist because empirical-Bayes entry priors, playoff-bracket conditioning,
and scoring behavior at a new boundary needed to be measured and validated
against held-out seasons before M7 was trusted there. Two new boundaries most
likely means two more rounds of that same calibration work, not a mechanical
copy-paste of the existing one. This is the dominant cost of the expansion and
the part a real plan (not this study) would need to size.

## Plumbing: two leagues is assumed as a fixed pair, not a list

Roughly fifteen files reference `"eng-championship"` as a sibling to
`"eng-premier-league"`, and the assumption is sometimes a literal pair rather
than an open list:

- `pipeline.py`: `LEAGUES = ("eng-premier-league", "eng-championship")`
- `cli.py`: `choices=["eng-premier-league", "eng-championship"]`
- `live_forecast.py`, `simulation.py`: `championship = competition ==
  "eng-championship"` booleans that special-case Championship-only behavior
  (playoff display, field size) rather than dispatching on `league_rules()`
- `sanctions.py`: `FULL_SEASON`/`FULL_FIELD` dicts keyed by competition — already
  dict-shaped, so already additive

`prospective.py` is the encouraging counterexample — it already holds
`[(competition, config_path), ...]` as a list, so widening it to four entries
is a one-line change there. The rest needs the same treatment: turn "is this
the Championship" checks into rule lookups, and turn the hardcoded pair into a
list of competition IDs threaded through `operate`, the CLI, and simulation.
None of it is architecturally blocked; it is breadth-of-touch, not depth.

## Publication boundary

`configs/publication.toml` allowlists by *key* (`competition_id`, `competitions`,
etc.), not by competition value, and `site/data/forecasts/<snapshot>/<competition>.json`
is already one file per competition. Adding two more competitions is additive
here with no boundary redesign.

## Volume

Two divisions today: 44 clubs, ~932 modeled matches/season. Four divisions:
~92 clubs, ~2,036 modeled matches/season — roughly 2.2x the clubs and matches,
and a similar multiple on simulation/inference compute and API-Football polling.
Nothing here needs new infrastructure, just more of the current kind.

## Scope statement that would need to change

[north_star.md](../../north_star.md) and [mvp.md](../../mvp.md) both state the
product's scope as "the Premier League and Championship" / "both leagues" in
several places. That's a product decision to revisit deliberately if scope
expands, not a technical blocker — flagged here so it isn't missed later.

## Bottom line

No provider, architectural, or licensing blocker rules this out. Every data
source either already covers all four tiers or already has a known, tolerated
gap (Understat) that doesn't get worse by going further down the pyramid. The
real cost is calibration research at two new promotion/relegation boundaries —
comparable in kind to the multi-experiment effort the Championship boundary
already took — plus de-hardcoding the "two leagues" pair assumption across
roughly fifteen files. Feasible; not cheap; the promotion-boundary calibration
is the long pole, not the data or the plumbing.
