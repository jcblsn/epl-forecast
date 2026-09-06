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

## Sampled reference

Install the optional research extra through uv and run:

```sh
uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --output runs/m5-posterior-reference
```

The reference uses [NumPyro NUTS](https://num.pyro.ai/en/latest/getting_started.html)
with noncentered Gaussian innovations. Its score likelihood and separate
calendar-time processes match a production component. Each team enters at its
first appearance with the same population prior. The default subset is the
90 Premier League matches from August through October 2024; the posterior cutoff
is October 28. This deliberately does not test empirical promotion priors or
full-history accumulation of approximation error.

One fit fixes process/dispersion parameters; a second infers retention, innovation
SDs and dispersion under explicit Beta/lognormal priors. The second comparison
averages production conditional filters over 100 sampled hyperparameter draws.
It assesses state approximation conditional on uncertain parameters, not the
accuracy of the production finite-grid model weights. Both fits compare the same
final-time filtering posterior, avoiding a filtering-versus-smoothing mismatch.

Four chains each use 600 warmup and 800 retained samples. Eight independent
synthetic datasets also receive sampled reference fits; 200 receive production
coverage checks. The generator draws known states and scores from the same
prior and transition law. These are finite, short-subset diagnostics. The
[results](experiments/m5_quality_tilt.md) identify both encouraging state coverage
and a league-level shortfall; they do not certify universal calibration.
