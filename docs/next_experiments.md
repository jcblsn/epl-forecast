# Research queue

The [north star](north_star.md) governs priorities. M2 remains the reference;
M4 dynamic hierarchical attack/defense is now a functioning prototype. Keep the historical
data, chronological evaluation, live archives, score interface and core tests.
The [M2 search](experiments/m2_tuning.md) found little value in further tuning.

The [first M4 evaluation](experiments/m4_dynamic.md) is nearly tied with M2
overall and worse early in the season. Individual Championship performance adds
little over the learned promotion population. Continue this architecture; next
audit the entry proxy, reference scale and uncertainty approximation before
increasing model complexity. Posterior coverage under simulated known states is
a useful next diagnostic. Keep M2 as the operational default during that work.

| Architectural role | Next work | Evidence needed |
| --- | --- | --- |
| Hierarchical starting state | Implemented bridge; refine the noisy entry proxy and pooling, then retain useful individual Championship signal. | Entry performance versus incumbents, Championship signal, carryover uncertainty, and how quickly PL evidence changes the prior. |
| Dynamic team state | Implemented sequential attack/defense; validate uncertainty and diagnose early-season adaptation. | Rolling comparisons with M2, early-season and promoted-team errors, calibration, response to changing form, and plausible state uncertainty. |
| State to score distribution | Preserve joint score likelihoods, grids and unbounded sampling. | Initially conditional Poisson; compact Dixon–Coles or overdispersion diagnostics only when they inform the mature likelihood. |
| State to season forecast | Implemented joint posterior draws per path. Investigate future evolution after current-state uncertainty is credible. | Coherent uncertainty across fixtures, deterministic-model compatibility and conserved table arithmetic. Hot evolution comes later. |
| Observations and priors later | Keep FPL snapshots; audit player history, then consider squad priors and persistent club quality. Treat shots/xG as observations of state. | Point-in-time coverage, stable definitions and incremental information. No detailed player model before the audit. |
| External information later | Keep structural and market-assisted products separate. | Matched forecast horizons and chronological evidence of incremental market information. |
| Live operation | Continue snapshots and forecast archives; expose new model states and uncertainty through the existing commands. | Forecasts archived before kickoff and explanations of changed estimates. No new scheduler or frontend work is needed. |

Use `idea → small implementation → rolling CV → inspect errors → iterate`.
All historical seasons can supply development evidence. Any parameter selection
must use earlier seasons when evaluating the selected strategy. Bridge fitting
must likewise exclude the target season's future PL results and Championship
records unavailable at the cutoff. Inspect per-season proper scores and
calibration alongside useful slices; aggregate log loss is not the only decision.

Archived live forecasts are the forward test. Retain per-match predictions and
disclose market horizons. Short result tables suffice for exploration; experiment
registries, frozen gates and extensive reproduction ceremony are unnecessary.

Deprioritize more Elo variants, larger M2 searches, manager/news features,
elaborate market assimilation and obscure European qualification edge cases.
Keep honest position probabilities and conditional cup scenarios for now.
