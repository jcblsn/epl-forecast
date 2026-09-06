# M5 Bayesian Quality–Tilt

M5 preserves M4's Gaussian filtering infrastructure and promoted-population prior.
It uses Q=(attack+defense)/2 and T=(attack-defense)/2. Home and away log rates are
mu + HFA + Q_home - Q_away + T_home + T_away and
mu - Q_home + Q_away + T_home + T_away. Q describes relative strength; T describes
openness. Both are relative to the inherited league prior, without a new recentering
constraint. Rating standard deviations include within- and between-model uncertainty.

Quality and Tilt each have their own annual retention and innovation standard
deviation. League scoring and home advantage have separate slow random walks.
An equally weighted prior over 12 combinations spans two Quality processes, two
Tilt processes and three Gamma shape values. Chronological joint daily predictive
likelihoods update the weights. These likelihood integrals use a Laplace
approximation, so the weights are approximate Bayesian probabilities, not exact
marginal likelihoods. No future scores enter parameter weighting. The independent
Poisson comparison averages over the same four unique dynamics processes.

Given state-dependent rates, one Gamma(k,k) tempo multiplies both scoring rates.
The resulting negative-multinomial score distribution has negative-binomial
marginals and positive conditional covariance. Its exact probability mass and
sampling retain unbounded scores. H/D/A probabilities sum over total goals with
less than 1e-12 omitted mass per Gaussian quadrature node. The exported square
score grid reports its own omitted mass. Gaussian quadrature integrates uncertain
log rates. The construction follows the shared exposure derivation discussed in
[this multivariate count-data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC5365157/).

Each simulated season samples a dynamics specification and joint current state,
then evolves that state through actual fixture dates. A new independent tempo is
sampled per match. Simulated scores do not feed back into sampled latent states.
Future match predictions use the same marginal transition law. Newly promoted
clubs use the frozen cohort distribution; individual Championship regressions
are not being refined in this batch.

Run through the existing pipeline:

```sh
uv run epl-forecast evaluate --config configs/quality_tilt.toml \
  --split holdout --output runs/m5-holdout
uv run epl-forecast forecast --config configs/quality_tilt.toml \
  --model M5-quality-tilt-v1 --snapshot snapshots/<UTC timestamp>
```

Live JSON and CSV expose Q, T, standard deviations and covariance. Match JSON
separates variance from uncertain rates, shared match tempo, and conditional
Poisson randomness. Season archives identify forward state evolution.
M2 remains the default. Historical diagnostics, sampled posterior validation and
synthetic coverage are necessary before claiming that M5 uncertainty is calibrated.
