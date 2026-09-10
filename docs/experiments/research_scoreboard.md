# Match research scoreboard

This is the permanent matched view of the operational M2 benchmark, retained M5
and M7 structural candidates, and average pre-closing and closing markets. It
reuses the 1,140 retained chronological forecasts from 2023/24–2025/26. All rows
below use the exact fixture intersection. These historical results are descriptive
research evidence; the reconstructed next-day xG horizon and source odds horizons
are not prospective publication timestamps.

| Forecast | H/D/A log loss | Brier | Classwise ECE | Score NLL |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.98039 | 0.58378 | 0.02055 | 2.98251 |
| M5 Poisson | 0.98250 | 0.58516 | 0.02849 | 2.97448 |
| M7 xG | 0.97827 | 0.58153 | 0.03598 | 2.97217 |
| Average pre-closing market | 0.96502 | 0.57401 | 0.02037 | — |
| Average closing market | 0.95973 | 0.56989 | 0.01809 | — |

M7 is the best retained structural match model on the pooled window. It improves
log loss by 0.00212 versus M2, closing 13.8% of the M2-to-pre-closing-market gap
and 10.3% of the M2-to-closing-market gap. That corresponds to a 0.21% increase
in geometric mean probability assigned to the realized outcome. M5 improves score
likelihood but trails M2 by 0.00211 in H/D/A loss. The tradeoff remains visible
rather than being collapsed into one promotion decision.

Season variation is material. M7 trails M2 by 0.00450 in 2023/24, gains 0.01349 in
2024/25 and trails by 0.00263 in 2025/26. The average pre-closing market beats M2
by 0.01538 across the full window and the average closing market by 0.02066. For
scale, a 0.001 log-loss gain changes the geometric mean realized probability by
about 0.10%; a 0.005 gain changes it by about 0.50% and would close 32.5% of this
window's structural-to-pre-closing gap.

The machine-readable artifacts include pooled metrics, per-season metrics, fixed-bin
calibration and the requested comparison columns:

- [`overall.csv`](research_scoreboard/overall.csv)
- [`by_season.csv`](research_scoreboard/by_season.csv)
- [`calibration.csv`](research_scoreboard/calibration.csv)
- [`comparisons.csv`](research_scoreboard/comparisons.csv)
- [`manifest.json`](research_scoreboard/manifest.json)

Rebuild the files from their retained inputs with:

```sh
uv run python scripts/build_scoreboard.py \
  --predictions docs/experiments/m8/chronological_predictions.csv.gz \
  --markets docs/experiments/m8/chronological_market_predictions.csv.gz \
  --output runs/research-scoreboard
```

The fraction of the market gap closed is a scale diagnostic, not a target or a
significance gate. Confirmation and deployment claims still require cutoff-safe
chronological evidence and prospective scoring.
