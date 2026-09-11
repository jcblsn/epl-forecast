# Validation

Four kinds of evidence support M7. This page gives the results and the commands to reproduce them.

1. Product checks on every forecast archive.
2. Historical season panels in all four divisions.
3. A match scoreboard in the Premier League.
4. The prospective ledger.

All historical forecasts on this page were made by code commit `fc94353` with the product configuration. The compact results are in [`evidence/`](../evidence/README.md).

## Product checks

Every archive must pass the checks in the [product contract](mvp.md) before publication. A failed check stops the publication. These checks do not measure skill. They show that each forecast is internally consistent: probabilities, event totals, rules, sanctions, playoff conditioning and provenance.

<!-- SEASON PANELS -->

## Match scoreboard

All forecasts below cover the same 1,140 Premier League matches in 2023/24–2025/26. Each model refits every day with earlier results only. Lower is better.

| Forecast | H/D/A log loss | Brier | Classwise ECE | Score NLL |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.98039 | 0.58378 | 0.02055 | 2.98251 |
| M7 | 0.97857 | 0.58167 | 0.03442 | 2.97278 |
| Average pre-closing market | 0.96502 | 0.57401 | 0.02037 | — |
| Average closing market | 0.95973 | 0.56989 | 0.01809 | — |

Over the full window, M7 has a lower log loss, Brier score and score NLL than M2. The gain is small: 0.0018 in log loss. M7 is not better in every season:

| Season | M2 log loss | M7 log loss | Pre-closing market log loss |
| --- | ---: | ---: | ---: |
| 2023/24 | 0.92936 | 0.93412 | 0.90925 |
| 2024/25 | 0.98533 | 0.97337 | 0.97055 |
| 2025/26 | 1.02649 | 1.02821 | 1.01525 |

The calibration error of M7 is higher than that of M2. Both models are worse than the betting market. For this reason, the market-assisted probability uses the market price with weight 1.0. See [methodology](methodology.md#market-assisted-probabilities).

Match scores are only a part of the case for M7. The difference between the models is larger in the season panels, because the state uncertainty of M7 matters most for season distributions.

## Prospective ledger

`site/data/ledger.json` scores each published match forecast after the result. It uses the last snapshot made before the kickoff. The ledger started on 10 September 2026. It has too few matches for a conclusion. It will become the main test of the product.

## Method

- Forecast origins: the first match day, and the day after the 6th, 12th, 19th and 30th nominal round. The rounds are proxies from match counts, not official rounds.
- Each origin fits the model from the start, with the results before the origin only. The simulation uses the recorded future schedule, not future results.
- Truth is the realized final table with every sanction in force at the end of the season. In the EFL divisions, the observed playoff winner is also truth.
- A forecast applies only the sanctions known at its origin.
- Rank RPS scores the whole position distribution. Points CRPS scores the whole points distribution. Coverage is the share of final totals inside the central interval.
- Each interval resamples whole seasons 10,000 times. The club-seasons in one season are not independent.
- This is retrospective evidence. The model specifications were developed with the same history. Results and xG are assumed available on the day after each match.

## Reproduce

Without provider data, rescore a committed season panel:

```sh
uv run python scripts/rescore_seasons.py --archive evidence/season_panels/eng-league-one/forecast_marginals.json.gz --output runs/rescore-league-one
uv run python scripts/report_seasons.py --evaluation runs/rescore-league-one --output runs/rescore-league-one/report
```

With the local data archive, run a season panel again and archive it:

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/evaluate_seasons.py --competition eng-league-one --models M2 M7 --seasons 2015 2016 2017 2018 2021 2022 2023 2024 2025 --output runs/panel-league-one
uv run python scripts/archive_seasons.py --evaluation runs/panel-league-one --output evidence/season_panels/eng-league-one/forecast_marginals.json.gz
```

The Premier League and the Championship use the default seasons, 2015/16–2025/26. League One and League Two leave out 2019/20 and 2020/21, because the curtailed 2019/20 season has no complete table.

With the local data archive, run the match scoreboard and refit the market pool:

```sh
uv run epl-forecast evaluate --split validation --output runs/match-validation
uv run epl-forecast evaluate --split holdout --output runs/match-holdout
uv run python scripts/fit_market_pool.py --predictions <predictions> --markets <market predictions> --output runs/market-pool
```

For `fit_market_pool.py`, join the `predictions.csv` and `market_predictions.csv` files of the two splits. With the predictions of commit `fc94353`, the refit gives a weight of 1.0 over 1,140 matches. It reproduces `configs/market_pool.json` exactly.

The detailed studies behind the model choices are on the research branch. See [research history](research.md).
