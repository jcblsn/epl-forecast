# M5 uncertainty investigation for M6

September 6, 2026. The bounded investigation found both a grid support limitation
and a posterior-mean bias, with different implications. M2 remains operational.
Production M5 inference and its original specification weights are unchanged.
Full numerical evidence is summarized in [this report](m6/m5_uncertainty.json).

## Grid support and likelihood integration are separate questions

Eight fixed probes extend the original winning corner toward lower Quality/Tilt
innovation, lower retention, Gamma shape 300 and independent Poisson. With equal
prior mass, the Poisson probe receives 67.23% weight at July 2023 and 84.64% at
July 2026; shape 300 receives 28.19% and 14.92%. Halving Quality innovation is
strongly disfavored, while reducing Tilt innovation is only weakly distinguished
from the original corner when dispersion is held fixed. Effective support is
1.88 at the first checkpoint and 1.35 at the last. The original near-single-model
weight does not establish that its finite dispersion grid is comprehensive.

These are exploratory full-history Laplace weights, not tuned production priors.
The Poisson direction was already favored before the 2023/24 pilot, consistent
with the previously retained score-likelihood ablation. The existing independent
Poisson M5 is the appropriate primary parent comparison for M6; shared tempo
remains available as an ablation and is not removed.

Separately, 4,096 scrambled Sobol importance draws reintegrate each daily joint
likelihood under the unchanged Gaussian prior of the production filter, across
760 matches in 2024/25–2025/26. Three independent scrambles give cumulative
log-evidence corrections of approximately -0.783 for the original corner,
-0.873 for Poisson, and -1.111 for the higher-innovation probe. Across-scramble
standard deviations are 0.0053, 0.0046 and 0.0021, and the minimum effective
sample fraction exceeds 0.82. The correction changes the Poisson/corner evidence
gap by about 0.09 log units and does not reverse their ranking. This checks daily
integration error conditional on the approximate priors, not exact long-history
Bayesian evidence or all accumulated state-approximation error.

## Common scoring level reveals a posterior-mean bias

League level and average Tilt have mean posterior correlation -0.747 in 200
prior-predictive synthetic 90-match datasets. A league shift of c and common
Tilt shift of -c/2 leave both match log rates unchanged instantaneously. The
prior and unequal dynamics constrain this direction over time.

That dependence does not explain away the coverage shortfall. Coverage of the
forecast-relevant common scoring level, league + twice average Tilt, is lower
than coverage of league alone:

| Nominal 90% interval | Original filter | Moment correction |
| --- | ---: | ---: |
| League level | 83.5% | 86.5% |
| Average Tilt | 87.5% | 87.5% |
| League + twice average Tilt | 79.5% | 90.5% |
| Individual match log scoring rates | 89.28% | 90.30% |

For common scoring level, replicate-based standard errors are 2.86 and 2.08
percentage points. Its mean standardized error falls from +0.821 to +0.129.
Individual-rate mean standardized error falls from +0.207 to +0.019. The
correction uses weighted posterior means and covariances from the daily
importance integral, then projects back to a Gaussian. It remains approximate.

A same-cutoff, fixed-dynamics NumPyro reference uses four chains, 600 warmup and
800 retained samples each. There are no divergences, maximum R-hat is 1.0010,
and minimum effective sample size is 2,215. Across the scoring functionals,
posterior-mean RMS discrepancy falls from 0.05679 to 0.01241 log-rate units;
the maximum standardized discrepancy falls from 0.597 to 0.112. This supports
a specific mode-versus-mean approximation problem rather than wholesale
replacement of the fast architecture. It does not validate promotion entry
uncertainty or a full-history corrected filter.

## Forecast consequences and decision

At November 1, 2024, using the same fresh-population opening-season fit and
fixed dynamics, correction changes the next Bournemouth–Manchester City log
rates by -0.0723 and -0.0570. Draw probability rises from 24.667% to 25.677%.
In 5,000 evolving-season paths per method, maximum mean-points difference across
clubs is 0.394 points; 5th/95th-percentile points endpoints differ by at most two
points. Those small season differences include Monte Carlo noise and are not
an assertion of equivalent distributions or calibrated season uncertainty.

Keep production fast inference and M2 operational. Carry the explicit common
scoring-level bias into M6 validation; daily moment correction is a credible
research alternative for chronological comparison, not a silently promoted fix.
The tested integration correction does not explain the original weight
concentration, while extending support toward Poisson does change the weights.

Reproduce with fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/investigate_m5_uncertainty.py \
  --output runs/m5-uncertainty-v1
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/investigate_m5_uncertainty.py \
  --output runs/m5-uncertainty-correction-v1 \
  --sections corrected_coverage sampled_sensitivity
uv run pytest tests/test_quality_tilt_uncertainty.py
```

The retained full reports include daily integrals and season distributions;
their hashes are in the committed summary. Numerical integration tests compare
the importance evidence, posterior mean and variance against scalar quadrature,
and verify that evidence-only diagnostics leave production states unchanged.
