# North star

Build a real-time probabilistic model of Premier League football, comparable in
functional ambition to PELE and adapted to club football. This is a capability
target, not a reproduction specification. Forecasts and their explanations are
the product; historical evaluation and archived forward forecasts guide changes.

| Stage | Capabilities |
| --- | --- |
| Current baseline | M2 fixed-strength attack/defense Poisson; season simulation conditional on one fitted strength vector; chronological evaluation; PL/Championship history; timestamped live snapshots and forecast archives. |
| Near term | M4 dynamic latent attack/defense, a learned Championship-to-PL promotion prior, approximate posterior state distributions, joint score predictions, and season simulations drawing one shared team state per path. |
| Eventual | Player-aware hierarchical priors, persistent club/system quality, Tilt/openness, richer correlated scoring, posterior and hot season simulations, and optional market assimilation. |

The central object is a distribution over changing team quality. Match evidence
updates it; Championship and prior-season performance inform its starting point.
Player quality should later inform priors, while shots and xG are candidate
observations. Squad and persistent club/system contributions should eventually
be distinguishable, so transfers, availability and lineups can change forecasts.
Audit historical player data before building this layer; keep capturing FPL now.

Translate latent state into a joint goal distribution, then into match and table
probabilities. Begin with conditional independent Poisson goals to isolate the
strength model. Later investigate finishing, goalkeeping, Tilt, overdispersion,
low scores and scoring correlation. Dixon–Coles is a diagnostic benchmark.

Season forecasts should integrate both match randomness and uncertainty in team
strength. A first posterior simulation holds one sampled state throughout each
season path. Hot simulation may later evolve that state or update it using
simulated results. Neither player availability nor future evolution is implied
by merely drawing the current posterior.

Keep structural football forecasts separately measurable from market-assisted
forecasts. Eventually ingest new information, update states, archive forecasts
and explain changes through results, squad changes, market information or
narrowing uncertainty.

Choose work that either becomes part of this architecture or supplies evidence
needed to choose it. Prefer a functioning vertical slice over polishing a local
baseline improvement. Use defensible approximate inference before considering a
large probabilistic-programming dependency.
