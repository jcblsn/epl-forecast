# Forecast MVP

The active product uses M7 as its structural match and season model in all four
divisions: the Premier League, Championship, League One and League Two. M2 remains
the operational comparison benchmark.
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
histograms are close to uniform where M2's are U-shaped. In the Championship, M7's
Understat channel contributes no evidence, so what carries over is its dynamics and
entry handling, not its observation model.

The [four-division panels](experiments/four_division.md) make the same choice
explicit in League One and League Two. M7 has lower rank RPS than M2 at every origin
in both. The difference is resolved at every origin in League One and at MW6 in League
Two, and no event Brier favours M2 resolvedly. M7's 90% points intervals cover 84–90%
where M2's cover 65–86% early in the season. The largest gains are for clubs
relegated into each division. One model serves all four divisions. Each division's
entry priors read only the divisions validated as useful for it; League One stays
out of the Championship, where its source term did not help promoted clubs.

The [2026/27 snapshot](experiments/current_season_projection_2026-09-10T18/report.md)
is the durable M7 season-distribution snapshot for the top two divisions, taken
before the scope widened; the
[earlier snapshot](experiments/current_season_projection_2026-09-10/report.md) from
the same day is retained as published and predates the sanction and playoff
corrections.

M7 is frozen as the structural season model for every division. Structural-model
improvement work is closed for now: the product path is prospective operation,
immutable forecast accumulation and comparison against public models, bookmaker
outrights and liquid prediction markets. The
[current-strength study](experiments/current_strength.md) is the standing
post-MVP research lead; it is not a build. Further player, current-strength or
cross-division work resumes from observed product deficiencies, not from a queue.

Every current M7 archive contains:

- structural H/D/A probabilities and a structural exact-score matrix;
- market-assisted H/D/A probabilities where a captured pre-closing quote exists;
- full final-points and final-position distributions for every club;
- expected and median points and rank, plus central 50%, 80% and 90% intervals;
- title, top-four, top-five and relegation probabilities for the Premier League;
- title, automatic-promotion, playoff-qualification, promotion and relegation
  probabilities for the Championship, League One and League Two, under each
  division's own places;
- the provider observation cutoff, generation timestamp, input provenance and a
  pre-kickoff archive manifest;
- any postponed or undated fixture, disclosed and simulated on the cutoff day until
  the provider re-dates it.

M7 is the primary forecast surface for near-term H/D/A probabilities, exact scores,
team states and season paths. The market-assisted arm remains separately labeled
comparison evidence when its required quote exists.

Playoff promotion in each EFL division simulates the edition-specific bracket
conditional on each regular-season path, on that path's own latent team states: the
Championship's six-team 2026/27 bracket and the four-team brackets of League One and
League Two. Neutral-final and tied-knockout treatments remain explicit approximations,
separate from fitting.
The [conditioning validation](experiments/playoff_conditioning.md) confirms that
this leaves points and rank distributions untouched.

Realized and current tables carry the sanctions in force, and forecasts carry only
the sanctions knowable at their cutoff, in every division. `scripts/verify_forecast_product.py`
re-checks a published archive against every claim on this page.

Run the four products with:

```sh
uv run epl-forecast forecast --competition eng-premier-league
uv run epl-forecast forecast --competition eng-championship
uv run epl-forecast forecast --competition eng-league-one
uv run epl-forecast forecast --competition eng-league-two
```

`uv run epl-forecast operate` runs all four, verifies each archive against this page
and publishes the derived surface described in
[operating the forecast product](product.md). Published snapshots are immutable,
carry at least 1,000 simulated paths, and are scored prospectively once their
matches settle.

Each archive also conditions the headline season events on the outcome of every
remaining fixture inside a seven-day horizon, by partitioning the same season
paths rather than re-simulating. These are conditional forecasts on one run, not
causal effects of a result, and the verifier re-checks that the outcome-weighted
conditionals return the published event.

The [match scoreboard](experiments/research_scoreboard.md),
[market-pool evaluation](experiments/market_pool.md), and
[season scoreboard](experiments/season_scoring.md) retain the selection evidence.
The [discovery sprint](experiments/discovery_sprint.md) records why no further
architecture build is on the MVP critical path.
