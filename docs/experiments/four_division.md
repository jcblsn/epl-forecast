# Four divisions: adding League One and League Two

The product now forecasts all four divisions of the English league pyramid. The
[feasibility study](efl_expansion/report.md) found no blocker and named calibration
at the new promotion and relegation boundaries as the main cost. This page records
what was added, what the calibration found, and the one place it changed the plan:
League One stays out of the Championship model.

## Decision

- M7 is the structural season model in every division, and M2 is the benchmark in
  every division. The [season panels](#season-panels) are the evidence for League
  One and League Two.
- One transition-aware entry rule (`memory`) still covers every boundary crosser.
  Each division's filter sees only the divisions validated as useful for it:
  | Forecast division | Divisions its entry priors can read |
  | --- | --- |
  | Premier League | Premier League, Championship |
  | Championship | Premier League, Championship |
  | League One | Championship, League One, League Two |
  | League Two | League One, League Two |
- The Championship keeps its two-division entry rule. Adding League One as a source
  division did not improve Championship forecasts for promoted clubs; it slightly
  worsened them and widened their intervals.
- Postponed fixtures no longer block a season projection. Until the provider gives a
  new date, a postponed fixture is simulated on the model cutoff day, and the archive
  says so.

## What was added

- **Registry.** `src/epl_forecast/competitions.py` holds each division's ID, name,
  tier, field size and provider codes. Every hard-coded Premier League/Championship
  pair now reads from it: the collectors, rules, sanctions, simulator, verifier,
  CLI, `operate` and the prospective capture.
- **Data.** Football-Data E2 and E3 results, 2010/11–2026/27. API-Football leagues
  41 and 42: teams, standings and fixtures for 2015/16–2026/27, plus the usual
  current-season collection. The team registry gained 46 clubs, reviewed from both
  providers' spellings, and three API-Football aliases. League One and League Two have
  no Understat xG and no FPL data, as with the Championship. The player and process
  research models (M5, M6, M8) run only in the top two divisions.
- **Rules.** Taken from the retained EFL Regulations 2026/27, reviewed at sections
  5.2, 7.8 and 9.1–9.9, 10.1.2 with its guidance, and 10.1.3–10.1.4:
  | Division | Automatic promotion | Playoff places | Relegated |
  | --- | ---: | ---: | ---: |
  | League One | 2 | 3rd–6th | 4 |
  | League Two | 3 | 4th–7th | 2 |

  Both run a four-team, five-match bracket: two-legged semi-finals of the first
  playoff place against the fourth, and the second against the third, then a final.
  The bracket code now starts below each division's automatic places, so one code
  path serves all three EFL divisions. The Championship's 2026/27 six-team bracket
  is unchanged.
- **A provider disagreement.** One fixture in the whole lower-tier history
  disagrees across providers. For Accrington Stanley v Sunderland in League One
  2018/19, API-Football records 1-1 on 2018-12-08 and Football-Data records 0-3 on
  2019-04-03. API-Football's own retained final standings reconcile only with the
  Football-Data record. `data/api_fixture_disputes.json` marks the API record's
  result and date unknown and surfaces it as a normalization issue, and the
  Football-Data record stands.
- **Sanctions.** Three deductions appear in complete lower-tier final tables:
  Reading −6 and Wigan Athletic −8 in League One 2023/24, and Morecambe −3 in League
  Two 2023/24. The reviewed registry carries their magnitudes. Their decision dates
  were not established, so no historical forecast applies them, but they are in the
  truth tables. The curtailed 2019/20 seasons show Bolton Wanderers −12 and
  Macclesfield Town −13, which no complete table confirms.
- **Ingestion edges met on the way.** Latest-odds rows captured before this archive
  held a division's schedule stay unlinked and are counted as a normalization issue.
  One League Two squad entry had no provider player ID; it is recorded as unknown
  rather than failing the whole squad.

## Entry priors at the new boundaries

`scripts/evaluate_entry_prior.py` ran the same matched design as the
[entry-prior comparison](entry_prior.md): the M7 fixed-p=0.2 parent, 4,000 paths,
scored at preseason and MW6. The only change between arms is the prior given to
clubs entering the division. League One and League Two cover 2016/17–2018/19 and
2021/22–2025/26: 104 boundary crossers and 923 opening appearances. The curtailed
2019/20 season and 2020/21, whose preceding season is incomplete, are excluded.

| Preseason, 104 crossers | Rank RPS | Points CRPS | 90% coverage | 90% width |
| --- | ---: | ---: | ---: | ---: |
| current (retained state) | 0.1765 | 9.082 | 92.3% | 54.75 |
| population | 0.1780 | 9.469 | 99.0% | 72.47 |
| transition | 0.1584 | 8.407 | 86.5% | 42.80 |
| source | 0.1562 | 8.288 | 87.5% | 43.31 |
| memory | 0.1573 | 8.342 | 88.5% | 43.87 |

Paired differences below use 95% season-clustered intervals:

| Crossers | Comparison | Rank RPS | Points CRPS |
| --- | --- | --- | --- |
| Preseason | memory − current | −0.0192 [−0.0324, −0.0051] | −0.740 [−1.474, −0.045] |
| Preseason | source − transition | −0.0022 [−0.0060, +0.0012] | −0.119 [−0.288, +0.033] |
| Preseason | memory − source | +0.0011 [−0.0003, +0.0028] | +0.054 [−0.014, +0.135] |
| MW6 | source − transition | −0.0019 [−0.0041, −0.0001] | −0.104 [−0.211, −0.016] |
| MW6 | memory − source | +0.0004 [−0.0015, +0.0021] | −0.000 [−0.084, +0.078] |

In the lower divisions, three things hold:
- Any learned entry prior clearly beats letting an entrant keep its old state.
- The source-division term earns its place: it is better at preseason and resolvedly
  better at MW6.
- The memory term adds nothing measurable. It is resolvedly worse only for clubs
  relegated from the Championship at preseason (+0.0024 [+0.0003, +0.0051] rank RPS).

`memory` stays the single rule, because the pooled difference from `source` is
within noise. The subgroup result is the lead to revisit if the rule is ever split.

In the Championship, the new `two_division` arm reproduces the frozen product
rule: `memory` fitted with only the Premier League and Championship visible.
Setting four-division `memory` against it isolates what League One adds.

| Championship, 60 crossers | Rank RPS, preseason | Points CRPS, preseason | Rank RPS, MW6 |
| --- | ---: | ---: | ---: |
| memory, four divisions visible | 0.1540 | 8.626 | 0.1351 |
| two_division (the product) | 0.1473 | 8.324 | 0.1313 |

Four-division `memory` minus `two_division`:
- Preseason: +0.0067 [−0.0020, +0.0170] rank RPS and +0.30 [−0.07, +0.76] points
  CRPS. The 90% interval widens by 1.95 points [0.20, 5.18].
- MW6: +0.0038 [−0.0004, +0.0080] rank RPS.

About half the preseason gap comes from three clubs promoted from the curtailed
2019/20 League One season. With no complete source season they form an undersized
`outside` cohort and fall back to the flat population prior. The other half comes
from clubs promoted from League One. For them the source term does not help:
+0.0065 [−0.0059, +0.0187] rank RPS, with intervals widened by 0.56 points
[0.22, 0.93]. Promoted clubs arrive clustered at the top of League One, so their
source strengths say little about how they will fare a division up. Nothing here
favours changing the frozen Championship rule, so League One stays out of its
training set.

## Season panels

`scripts/evaluate_seasons.py` scored M7 against M2 in each lower division over the
same nine seasons: 2015/16–2018/19 and 2021/22–2025/26. Each forecast uses 24 clubs,
five origins and 10,000 paths. Scoring is against sanctioned final tables and the
observed playoff winners, giving 216 club-seasons per model and origin. Intervals
are 95% season-clustered intervals on the M7 − M2 difference.

League One:

| Origin | Rank RPS M2 | Rank RPS M7 | M7 − M2 | Points CRPS M2 | Points CRPS M7 | M7 − M2 | 90% coverage M2 / M7 |
| --- | ---: | ---: | --- | ---: | ---: | --- | ---: |
| preseason | 0.1715 | 0.1518 | −0.0197 [−0.0312, −0.0087] | 9.456 | 8.494 | −0.96 [−1.55, −0.44] | 64.8% / 83.8% |
| MW6 | 0.1364 | 0.1255 | −0.0109 [−0.0167, −0.0042] | 7.489 | 7.126 | −0.36 [−0.75, +0.04] | 67.6% / 83.8% |
| MW12 | 0.1162 | 0.1084 | −0.0078 [−0.0116, −0.0043] | 6.620 | 6.253 | −0.37 [−0.61, −0.16] | 70.8% / 85.2% |
| MW19 | 0.0951 | 0.0910 | −0.0041 [−0.0075, −0.0006] | 5.208 | 5.128 | −0.08 [−0.26, +0.10] | 77.3% / 87.5% |
| MW30 | 0.0646 | 0.0623 | −0.0023 [−0.0043, −0.0007] | 3.490 | 3.440 | −0.05 [−0.12, +0.03] | 82.9% / 85.6% |

League Two:

| Origin | Rank RPS M2 | Rank RPS M7 | M7 − M2 | Points CRPS M2 | Points CRPS M7 | M7 − M2 | 90% coverage M2 / M7 |
| --- | ---: | ---: | --- | ---: | ---: | --- | ---: |
| preseason | 0.1719 | 0.1609 | −0.0110 [−0.0261, +0.0035] | 8.033 | 7.576 | −0.46 [−0.95, +0.04] | 69.4% / 89.4% |
| MW6 | 0.1471 | 0.1348 | −0.0123 [−0.0186, −0.0052] | 6.913 | 6.438 | −0.48 [−0.76, −0.15] | 74.5% / 90.3% |
| MW12 | 0.1138 | 0.1089 | −0.0049 [−0.0121, +0.0018] | 5.479 | 5.240 | −0.24 [−0.51, +0.05] | 79.6% / 88.9% |
| MW19 | 0.0966 | 0.0942 | −0.0024 [−0.0056, +0.0009] | 4.734 | 4.607 | −0.13 [−0.29, +0.04] | 82.9% / 90.3% |
| MW30 | 0.0687 | 0.0679 | −0.0008 [−0.0026, +0.0009] | 3.422 | 3.382 | −0.04 [−0.15, +0.06] | 86.1% / 89.8% |

M7 is the better season product in both divisions:
- **Rank RPS.** M7 has the lower rank RPS at every origin in both divisions. The
  difference is resolved at every origin in League One and at MW6 in League Two.
- **Event Briers.** In League One, M7 resolvedly improves the preseason Brier for
  automatic promotion (−0.013), playoff qualification (−0.008), promotion (−0.015)
  and relegation (−0.016). In League Two its relegation Brier is resolvedly better
  from preseason through MW19. No event Brier favours M2 resolvedly. At MW19 and
  MW30, M2's automatic-promotion point estimates are marginally better in both
  divisions, by 0.002 to 0.005.
- **Intervals.** M2's 90% points intervals are too narrow at every early origin.
  M7's sit at 84–90%, slightly short of nominal in League One.

The gain is largest where M2 has least to work with, namely clubs arriving from
another division. For clubs relegated into League One, M2 scores 0.1997 preseason
rank RPS with 40.7% coverage of its 90% interval; M7 scores 0.1489 with 88.9%. For
clubs relegated into League Two the figures are 0.2092 and 58.3% for M2, against
0.1805 and 94.4% for M7. Incumbents improve too, from 0.1645 to 0.1519 in League
One and from 0.1640 to 0.1568 in League Two. As in the Championship, no xG enters
either division, so the advantage comes from M7's dynamics, posterior uncertainty
and entry handling.

### Championship

The Championship panel was rerun twice under current code over 2015/16–2025/26,
giving 264 club-seasons per origin. The first run trains M7 on the two divisions the
product uses; the second adds League One and League Two. M2 is identical in both
runs, down to every club-season score, so the M7 difference isolates the lower
divisions.

| Origin | Rank RPS M2 | M7, two divisions | M7, four divisions | Points CRPS M7, two / four divisions |
| --- | ---: | ---: | ---: | ---: |
| preseason | 0.1632 | 0.1460 | 0.1481 | 7.554 / 7.645 |
| MW6 | 0.1415 | 0.1319 | 0.1328 | 6.891 / 6.945 |
| MW12 | 0.1238 | 0.1163 | 0.1169 | 6.053 / 6.077 |
| MW19 | 0.0991 | 0.0962 | 0.0965 | 4.901 / 4.911 |
| MW30 | 0.0634 | 0.0625 | 0.0625 | 3.306 / 3.315 |

The product configuration keeps the earlier Championship conclusion. M7 beats M2
resolvedly on rank RPS and points CRPS at preseason, MW6 and MW12:
−0.0172 [−0.0258, −0.0086] and −0.74 [−1.22, −0.24] at preseason. It also beats M2
on every preseason event Brier except relegation.

Adding the lower divisions worsens M7 at every origin, by 0.0021 rank RPS and
0.09 points CRPS at preseason, fading to nothing by MW30. That is the season-panel
counterpart of the entry-prior result above. It is why the Championship's
training set stops at the Premier League.

## Postponed fixtures

The lower divisions postpone fixtures routinely; League One's Oxford United v Reading
was postponed from 8 September 2026 when this was written. The earlier rule withheld
the season projection until every fixture had a date, which would block publication
for every division whenever one is waiting. A postponed or undated fixture is now:
- simulated on the model cutoff day;
- listed in the archive's `unscheduled_fixtures`, with its placeholder recorded in
  the simulation assumptions;
- checked by the verifier.

Re-dating moves only the date the two clubs' latent states are evolved to. With
annual retention near 0.85, that is a small shift for a single fixture. Fixtures in
play or awaiting a result still withhold the projection.

## Limitations

- **Curtailed seasons.** League One and League Two 2019/20 were decided on points
  per game, and their archives are incomplete. They yield no training cohort, no
  truth, and no source season for 2020/21 entrants.
- **Undated sanctions.** The lower-tier sanctions have no established decision
  dates, so historical forecasts apply none of them; truth applies all of them.
- **No lower-tier xG.** No lower-division xG enters any model. M7's advantage there
  comes from its dynamics and entry handling, as in the Championship.
- **Player history.** API-Football player-level history for League One and League
  Two has not been backfilled. The product model does not use it; the player
  research models remain top-two only.
- **League Two relegation.** It can shrink under Regulation 10.1.3(b) if a National
  League club fails admission. The forecast reports the two-place table event.

## Reproduce

```sh
uv run epl-forecast data normalize
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_entry_prior.py \
  --competitions eng-championship --output runs/entry-prior-four-division/championship
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_entry_prior.py \
  --competitions eng-league-one eng-league-two \
  --treatments current population transition source memory \
  --seasons 2016 2017 2018 2021 2022 2023 2024 2025 \
  --output runs/entry-prior-four-division/lower
uv run python scripts/report_entry_prior.py runs/entry-prior-four-division/lower
for division in one two; do
  OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_seasons.py \
    --competition eng-league-$division --models M2 M7 \
    --seasons 2015 2016 2017 2018 2021 2022 2023 2024 2025 \
    --output runs/league-$division-season-scoring-v1
  uv run python scripts/report_seasons.py \
    --evaluation runs/league-$division-season-scoring-v1 \
    --output runs/league-$division-season-scoring-v1/report
done
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_seasons.py \
  --competition eng-championship --models M2 M7 \
  --train-competitions eng-premier-league eng-championship \
  --output runs/championship-season-scoring-two-division
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_seasons.py \
  --competition eng-championship --models M2 M7 \
  --train-competitions eng-premier-league eng-championship eng-league-one eng-league-two \
  --output runs/championship-season-scoring-four-division
uv run python scripts/compare_season_runs.py \
  --baseline runs/championship-season-scoring-two-division \
  --revised runs/championship-season-scoring-four-division \
  --output runs/championship-season-scoring-four-division/comparison
```

The four-division Championship run was started before the per-division training
table existed, so it trained on all four divisions through the config's flat list;
`--train-competitions` reproduces that.
