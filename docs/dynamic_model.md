# M4 dynamic hierarchical prototype

M4 is the first vertical slice toward the [north star](north_star.md). M2 remains
the default reference while M4 is evaluated. Both use the same score-generating
forecast interface. No new inference library is required.

## State and inference

The state contains a league log scoring level, home advantage, and attack and
defense for every club with observed PL results. Positive defense reduces the
opponent's scoring rate:

```text
log lambda_home = mu + home_advantage + attack_home - defense_away
log lambda_away = mu                  + attack_away - defense_home
```

Team states follow a Gaussian mean-reverting process in elapsed calendar days.
Annual retention is 0.85, with annual innovation SD 0.18. For elapsed years u,
F = 0.85^u and Q = 0.18² (1 - F²) / (1 - 0.85²). League level and home advantage
follow random walks with annual SD 0.06. Gaps therefore add uncertainty; prior
seasons persist. Initial club SD is 0.4; initial global means are log(1.2) and
log(1.3), each with SD 0.25. These are fixed prototype settings, not tuned results.

All matches on a date update jointly, after predictions for that date. A
Gaussian prior times the Poisson likelihood is approximated at its posterior
mode, with inverse-Hessian covariance. The implementation solves the small
observation-space problem and retains the full state covariance. This is a
first-order [Laplace Gaussian filter](https://pmc.ncbi.nlm.nih.gov/articles/PMC3132892/),
not posterior sampling of a complete latent trajectory. Proper Gaussian priors
anchor the reference scale; unlike M2, states are not constrained to sum to zero.
This reference is a model population, not necessarily today's league average.

M4 uses expanding PL/Championship history. Repeated fits append new days when the
input prefix is unchanged; revisions or earlier cutoffs trigger a complete
replay. All public fitting rejects same-day/future results. CLI and evaluation
share the same information selection. No future fixture identities initialize
the filter.

## Promotion hierarchy

Only complete 552-match Championship and 380-match PL seasons enter the bridge.
A previous Championship season is fit with division-relative attack/defense
(ridge 2, no decay); centered Laplace marginal variances describe uncertainty.

For each promoted club, its first ten PL appearances supply goals for/against
and opponent-adjusted exposures. Opponent strengths and league rates come from
that completed PL season. A scalar Poisson fit with a weak N(0, 1) prior gives
noisy entry attack and defense estimates. These are retrospective entry proxies:
the opponent reference uses the whole completed season, and entry quality can
already change within ten matches. They are not directly observed latent truth.

Separately for attack and defense, the bridge models entry strength as an
intercept plus a coefficient times Championship strength plus club residual.
Coefficient priors are N(0, diag(0.6², 1)); residual SD has a half-normal(0.3)
prior. One-dimensional quadrature integrates residual uncertainty, and Gaussian
regression moments integrate coefficient uncertainty. Three moment iterations
account approximately for uncertainty in Championship strength. The returned
team prior includes residual, coefficient and source-strength uncertainty.

The bridge used at entry contains only completed PL cohorts from earlier
seasons, available on that entry date. An incoming club uses its immediately
previous Championship season, including a returning club with stale PL ratings.
If the Championship season is incomplete or absent, the explicit fallback is
the broader league population prior. Before its first PL result, a club can be
predicted from its Championship prior without adding future fixture identities
to the fitted vocabulary.

This is a two-stage approximate hierarchy. Season summaries, fixed opponent
offsets, independent attack/defense bridge regressions and Gaussian moment
matching omit some uncertainty. Shared bridge-parameter covariance across
different promoted clubs is not retained in the filter. Dynamics parameters are
fixed, not integrated out. These limitations matter when interpreting intervals.

## Forecast and simulation boundary

Match predictions integrate the bivariate Gaussian log-rate distribution using
9 by 9 Gauss–Hermite quadrature. Conditional scores remain independent Poisson;
mixing over state uncertainty can induce marginal dependence and overdispersion.
This is epistemic mixing, not an estimated match-openness or correlated-goal
likelihood. H/D/A probabilities and observed-score likelihoods use the full goal
support; displayed grids retain omitted tail mass.

`sample_forecast_state(rng, size=1)` draws the joint current posterior. A batch
uses one array index per season path; `sample_scores(fixture, rng)` reuses those
states for every fixture. Incoming-club draws are also cached per path. The
simulator recognizes this optional capability; deterministic models retain the
existing path. Fixed played scores, probability conservation and tiebreakers
continue to apply.

Future fixtures condition on current strength. There is no future state drift,
result-driven hot updating, lineup uncertainty or market input yet. Live M4
exports label posterior simulation and include attack/defense SDs and entry
priors in JSON/CSV.

## Run

```sh
uv run epl-forecast evaluate --config configs/dynamic.toml \
  --split development --output runs/m4-development
uv run epl-forecast forecast --config configs/dynamic.toml \
  --model M4-dynamic-hierarchical-v1 --snapshot snapshots/<UTC timestamp>
uv run epl-forecast simulate --config configs/dynamic.toml \
  --model M4-dynamic-hierarchical-v1 --season 2024-2025 --as-of 2024-08-01 \
  --simulations 10000 --output runs/m4-season
```

Inspect per-season scores, promoted and early-season subsets, calibration,
state uncertainty and adaptation. Historical results are development evidence;
archived pre-kickoff forecasts remain the forward test.
