# Evidence

This directory holds the compact evidence behind [validation](../docs/validation.md). It contains only model output and realized results. It contains no provider payloads and no odds.

| Path | Content |
| --- | --- |
| `match_scoreboard/predictions.csv.gz` | M2 and M7 H/D/A forecasts for 1,140 Premier League matches in 2023/24–2025/26, with outcomes and score log-likelihoods. |
| `season_panels/<division>/forecast_marginals.json.gz` | The points and position distributions of every M2 and M7 season forecast, with the realized final tables. |
| `season_panels/<division>/forecast_marginals.json.index.json` | The hash, seasons and forecast count of the archive. |
| `season_panels/<division>/summary.csv` | Scores for each model and origin. |
| `season_panels/<division>/paired_comparisons.csv` | M7 − M2 differences with season-clustered 95% intervals. |

Code commit `fc94353` made all these forecasts, with the product configuration.

To rescore one division without provider data:

```sh
uv run python scripts/rescore_seasons.py --archive evidence/season_panels/eng-league-one/forecast_marginals.json.gz --output runs/rescore-league-one
uv run python scripts/report_seasons.py --evaluation runs/rescore-league-one --output runs/rescore-league-one/report
```

Do not edit these files by hand. Replace them only with the output of a new, recorded evaluation.
