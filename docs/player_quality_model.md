# M6 player Quality vertical slice

M6 retains dynamic club/system Quality and team Tilt, and jointly fits static
scalar player Quality with the daily goal likelihood. A player's coefficient
is multiplied by their share of observed team minutes. Independent Poisson is
the primary likelihood; shared Gamma tempo remains a constructor ablation.

The initial population hierarchy uses beta ~ Normal(0, 0.6²), with the scale
fixed before evaluation. A full-match player contributes approximately beta/11
to team Quality. Club and player posterior cross-covariances are retained;
regularizing priors resolve the otherwise weak club/roster decomposition.
These coefficients are goals-based conditional associations, not causal player
values. The first implementation keeps player effects static and does not add
player Tilt, individual xG, or transfer valuation.

Forecasts integrate a finite mixture of sampled candidate lineups with the
joint Gaussian posterior. Unseen and anonymous players receive population
uncertainty. Season paths draw persistent player coefficients once, evolve club
states over calendar time, and resample minutes at each fixture. Availability
uses the existing timestamped, expiring squad assumptions.

Historical fitting uses corrected actual minutes only for training matches.
Target-match actual minutes are exposed only through an explicitly requested
oracle score distribution. Deployable candidates use prior appearances or an
explicit timestamped squad snapshot. Historical publication times and opening
season membership remain limitations.

## Completion evidence and remaining work

The initial unit checks cover joint identification/covariance, incremental
replay with newly introduced clubs, cutoff isolation, a controlled expiring
absence, reduction to the parent posterior without player observations, and
agreement between direct probabilities and evolving sampled score frequencies.

This foundation is not yet the completed batch. Remaining deliverables are:

- Chronological unchanged-M5, deployable-M6 and oracle-M6 comparisons.
- Targeted lineup-change, absence, return, newcomer, promotion, early-season
  and goalkeeper diagnostics, including direction and size of movement.
- A manageable sampled Bayesian reference for the joint player approximation.
- Live export of club/player decomposition and lineup uncertainty.
- A timestamped current availability scenario with match and season deltas.
- Prospectively archived current M6 forecasts with source and artifact hashes.

M2 remains operational. M6 promotion requires separate chronological and
forward evidence; completing this batch does not imply promotion.
