# North star

Build a real-time probabilistic Premier League model comparable in functional
ambition to PELE and adapted to club football. This is a capability target, not
a reproduction specification. Forecasts and their explanations are the product.

M2 remains the operational reference. M5 now represents changing Quality and
Tilt, approximate uncertainty over states and dynamics, correlated overdispersed
scores, and coherent season trajectories. A limited sampled Bayesian reference
and historical rolling comparisons identify its current approximation limits.
The [M5 report](experiments/m5_quality_tilt.md) records the evidence.

The next main gap is squad information. Distinguish persistent club/system
quality from hierarchical player contributions and expected-lineup uncertainty.
The [player audit](player_data_audit.md) supplies fixture-level historical data
and identifies what cannot yet be reconstructed before an old match. Player
and squad information should eventually inform both Quality and Tilt; shots/xG
are candidate observations of those states.

Translate uncertain states into a joint score distribution, then into match and
table probabilities. Forward generative simulations evolve sampled latent states;
their simulated scores do not update already-sampled hidden strengths. Simulating
how an observer's public forecast changes after hypothetical results is a
separate operation requiring conditional filtering.

Keep structural and market-assisted forecasts separately measurable. Eventually
ingest results and squad changes, archive forecasts and explain changes. Choose
work that implements these capabilities or provides evidence needed to choose
them. Preserve fast approximate production inference when reference checks support
it. Historical evaluation and timestamped forward forecasts guide development;
there is no arbitrary minimum improvement gate.
