# Exploratory M2 tuning — 2026-09-05

Keep the current 365-day half-life and ridge 5. The parameter surface is flat
around half-lives 240–365 and ridge 2–5; the best fixed candidate has only a small
H/D/A gain and a worse score NLL. More parameter searching is lower priority than
promotion continuity and lagged shots.

Evaluated 30 combinations: half-life `{120, 240, 365, 540, 730}` × ridge
`{0.5, 1, 2, 5, 10, 20}`, retaining the 1,095-day history window. Daily fitting
excludes same-day results. The chronological selection strategy starts with
2015/16–2017/18 predictions and chooses parameters before each subsequent season
using mean log loss across all earlier seasons. The eight evaluation seasons are
2018/19–2025/26 (3,040 matches).

| Model | Log loss | Brier | Score NLL |
| --- | ---: | ---: | ---: |
| Current M2: half-life 365, ridge 5 | 0.97183 | 0.57702 | 2.95381 |
| Best fixed H/D/A candidate: half-life 240, ridge 2 | 0.97153 | 0.57681 | 2.95848 |
| Parameters selected using earlier seasons | 0.97287 | 0.57761 | 2.95716 |
| Bet365 pre-closing, same 3,040 fixtures | 0.95938 | 0.56827 | — |

The best fixed candidate is a descriptive optimum over the historical surface,
not an untouched test result. Chronological selection preferred 240/2 or 240/5 in
seven folds and 365/5 in one; selection was slightly worse than leaving the defaults
alone. The closing market scored 0.96388 on its 2,660-fixture coverage, versus
0.98298 for current M2 on the same rows. Market observation horizons differ from
our daily cutoff and individual quote times are unknown.

The [full aggregate table](m2_tuning.csv) retains all candidates. Per-match,
per-season, calibration, matched-market and selection outputs are in
`runs/m2-tuning/`. No bootstrap or acceptance gate was needed for this exploration.

```sh
uv run python scripts/tune_m2.py --output runs/m2-tuning
```
