# Market-assisted match forecast

The first market-assisted forecast uses the smallest chronological rule: de-vig the
average pre-closing H/D/A odds by proportional normalization, then combine those
probabilities with M7 using a one-parameter logarithmic pool. The weight is fitted
by H/D/A log loss. The structural score model and all season simulations remain
independent of market prices.

The rule was fitted on 760 matched fixtures from 2023/24–2024/25 and evaluated on
the later 380 fixtures in 2025/26. The fitted market weight is 1.0. On the later
season, market-assisted log loss is 1.01525, versus 1.02912 for M7; Brier is
0.61002 versus 0.61775. The result says the structural probability adds no value
to this deliberately small pool on current evidence. The resulting assisted arm
is therefore the de-vigged market probability whenever a suitable quote exists.
This boundary result is retained rather than forcing a structural contribution.

The final operational weight refits the same frozen rule on all 1,140 fixtures
through 2026-05-24 and remains 1.0. Historical Football-Data columns identify
pre-closing prices but do not preserve individual quote timestamps. This is valid
for the historical horizon comparison, not a claim about a precise hours-before-
kickoff horizon. Prospective archives retain the actual snapshot retrieval time.

[`pool.json`](market_pool/pool.json) contains the final fit and
[`evaluation.json`](market_pool/evaluation.json) contains the chronological split,
metrics and source hashes. Rebuild them with:

```sh
uv run python scripts/fit_market_pool.py \
  --predictions docs/experiments/m8/chronological_predictions.csv.gz \
  --markets docs/experiments/m8/chronological_market_predictions.csv.gz \
  --output runs/market-pool
```

Current M7 forecast archives expose primary structural probabilities and separately
labeled market-assisted probabilities, with the de-vigged source probabilities,
raw odds, quote retrieval time and pool weight retained for provenance. Exact scores
and long-horizon fixtures are always structural.
