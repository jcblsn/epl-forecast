# Research queue

M5 now supplies Quality/Tilt states, separate dynamics with approximate Bayesian
weights, shared-Gamma scoring, forward state trajectories, and a sampled
posterior reference. The [batch report](experiments/m5_quality_tilt.md) records
what these components achieved. M2 remains the operational reference.

The player/squad layer is the next main modeling project. Use the
[player audit](player_data_audit.md) to design M6 around persistent club quality,
hierarchical player contributions and uncertain expected minutes. Start the
full-feature pilot in 2023/24–2025/26. Fixture-time clubs and past appearances
are available; historical injury states, complete candidate squads and exact
publication-time replay still need evidence. FPL prices and fantasy points are
not substitutes for player quality.

Carry two concrete M5 findings into that work:

- The initial dynamics grid puts almost all historical posterior weight on one
  low-volatility, weak-overdispersion corner. Expand or assess support and check
  predictive-evidence approximation before interpreting the grid as comprehensive
  hyperparameter uncertainty. Do not artificially flatten weights to hide this.
- Synthetic Quality/Tilt interval coverage is close to nominal on the tested
  short subset, but league-scoring coverage is low. The reference supports the
  fast filter for now; investigate that identifiable approximation issue rather
  than replacing production inference wholesale. The sampled reference uses
  population initialization and does not validate promotion entry uncertainty.

Shared tempo adds a coherent correlated score law but does not improve initial
score likelihood against the Poisson ablation. Inspect draw and tail residuals
before adding a local score correction. Keep chronology in any subsequent
choice of dynamics or likelihood support.

Freeze the promoted-population prior. Individual Championship translation,
more Elo/M2 tuning, frontend work, schedulers, manager/news effects, market
assimilation and European qualification edge cases are not the next workstream.
Continue live captures and forecasts. Short diagnostic tables and retained
predictions are sufficient; no new experiment-governance process is needed.
