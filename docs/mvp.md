# Forecast MVP

The active product uses M7 as its structural match and season model for both the
Premier League and Championship. M2 remains the operational comparison benchmark.
This is a product choice from the combined scoreboard, not a claim that M7 wins
every metric or fixes the final architecture.

The matched match scoreboard favors M7 among retained structural forecasts:
0.97827 H/D/A log loss versus 0.98039 for M2, with better Brier and score NLL.
The 11-season season panel favors M7 on rank RPS at preseason, MW6, MW12 and MW19,
and on points CRPS at every evaluated origin after preseason. M4 has the best
preseason points CRPS and slightly wider early points coverage. M7 is the practical
single-model choice because it combines the best retained match score, strong rank
distributions, posterior state uncertainty and the best later-origin points scores.
The tradeoff remains recorded in the season artifacts.

Every current M7 archive contains:

- structural H/D/A probabilities and a structural exact-score matrix;
- market-assisted H/D/A probabilities where a captured pre-closing quote exists;
- full final-points and final-position distributions for every club;
- expected points and rank, their standard deviations, and central 90% intervals;
- title, top-four, top-five and relegation probabilities for the Premier League;
- title, automatic-promotion, playoff-qualification, promotion and relegation
  probabilities for the Championship;
- the provider observation cutoff, generation timestamp, input provenance and a
  pre-kickoff archive manifest.

The market-assisted arm is preferred for near-term H/D/A probabilities when its
required quote exists. It does not alter exact scores, team states or season paths.
When no suitable quote exists, the preferred probability fields fall back to M7.

Championship playoff promotion currently assigns the single playoff promotion
slot equally among the qualifiers on each simulated regular-season path. This
preserves three total promotion slots and keeps the assumption explicit. A future
playoff match model can replace it without changing the structural regular-season
simulation.

Run both products with:

```sh
uv run epl-forecast forecast --competition eng-premier-league
uv run epl-forecast forecast --competition eng-championship
```

The [match scoreboard](experiments/research_scoreboard.md),
[market-pool evaluation](experiments/market_pool.md), and
[season scoreboard](experiments/season_scoring.md) retain the selection evidence.
