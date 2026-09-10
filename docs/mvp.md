# Forecast MVP

The active product uses M7 as its structural match and season model for both the
Premier League and Championship. M2 remains the operational comparison benchmark.
This is a product choice from the combined scoreboard, not a claim that M7 wins
every metric or fixes the final architecture.

The matched match scoreboard favors M7 among retained structural forecasts:
0.97827 H/D/A log loss versus 0.98039 for M2, with better Brier and score NLL.
The 11-season Premier League season panel favors M7 on rank RPS at preseason, MW6,
MW12 and MW19, and on points CRPS at every evaluated origin after preseason. M4 has
the best preseason points CRPS and slightly wider early points coverage. M7 is the
practical single-model choice because it combines the best retained match score,
strong rank distributions, posterior state uncertainty and the best later-origin
points scores. The tradeoff remains recorded in the season artifacts.

The [Championship panel](experiments/season_scoring_championship.md) makes the
second league's choice explicit rather than inherited. M7 beats M2 there on rank
RPS at preseason, MW6, MW12 and MW19, on points CRPS through MW12, and on every
preseason event Brier, with season-clustered intervals excluding zero, and its PIT
histograms are close to uniform where M2's are U-shaped. One model serves both
leagues. In the Championship, M7's Understat channel contributes no evidence, so
what carries over is its dynamics and entry handling, not its observation model.

The [2026/27 snapshot](experiments/current_season_projection_2026-09-10/report.md)
is the current durable M7 season-distribution product for both leagues.

Every current M7 archive contains:

- structural H/D/A probabilities and a structural exact-score matrix;
- market-assisted H/D/A probabilities where a captured pre-closing quote exists;
- full final-points and final-position distributions for every club;
- expected and median points and rank, plus central 50%, 80% and 90% intervals;
- title, top-four, top-five and relegation probabilities for the Premier League;
- title, automatic-promotion, playoff-qualification, promotion and relegation
  probabilities for the Championship;
- the provider observation cutoff, generation timestamp, input provenance and a
  pre-kickoff archive manifest.

M7 is the primary forecast surface for near-term H/D/A probabilities, exact scores,
team states and season paths. The market-assisted arm remains separately labeled
comparison evidence when its required quote exists.

Championship playoff promotion simulates the edition-specific bracket conditional
on each regular-season path with the structural score model. Neutral-final and
tied-knockout treatments remain explicit approximations, separate from fitting.

Run both products with:

```sh
uv run epl-forecast forecast --competition eng-premier-league
uv run epl-forecast forecast --competition eng-championship
```

The [match scoreboard](experiments/research_scoreboard.md),
[market-pool evaluation](experiments/market_pool.md), and
[season scoreboard](experiments/season_scoring.md) retain the selection evidence.
The [discovery sprint](experiments/discovery_sprint.md) records why no further
architecture build is on the MVP critical path.
