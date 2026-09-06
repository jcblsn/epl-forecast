# Research queue

M6 now supplies the player-aware Bayesian vertical slice described in the
[batch report](experiments/m6_player_quality.md). M2 remains operational.
Independent-Poisson M5 is the primary parent; shared Gamma tempo remains an
ablation. Do not expand the M5 grid as the next project.

The first full chronological comparison does not establish a predictive gain.
Retain the strongly pooled player architecture for now. Opening-season and
newcomer diagnostics show that candidate membership and minutes are a real
bottleneck, while the flat full-season oracle result also leaves goals-only
player identification unresolved. Neither finding warrants player Tilt yet.

Continue timestamped 2026/27 squad, availability and forecast archives. Score
only fixtures whose forecasts were archived before kickoff, checking later
snapshots for rescheduling. Accumulate actual forward transfer/absence cases;
historical corrected appearances cannot substitute for those records.

Before extending the player model, inspect the learned club/player covariance,
coefficient shrinkage, and directional response to large real lineup changes.
A materially different second player formulation deserves a bounded test if
identification remains weak. If both formulations fail in oracle and
high-information slices, park further development rather than tune endlessly.
If xG becomes the next observation layer, compare to a team-only xG parent.

Keep the inherited common-scoring-level approximation bias bounded and explicit.
The sampled player reference supports the fast approximation on its manageable
subset; it does not justify moving production wholesale to MCMC.

Do not simultaneously add individual xG, player Tilt, market assimilation,
manager/news effects, frontend work or another lineup-sampler optimization batch.
