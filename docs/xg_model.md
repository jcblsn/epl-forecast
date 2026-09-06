# M7 team xG observation model

M7-v1 uses the [centered Quality/Tilt process](centered_quality_tilt_model.md)
and a joint goals/Understat-xG likelihood. M2 stays unchanged. This is a team-only
first formulation; no player, finishing or goalkeeping parameters are introduced.

## Generative assumptions

For each side, let lambda = exp(match log rate) from the dynamic team state.
Introduce a latent number of scoring opportunities N and observation-noise
parameter p:

```
N | lambda,p ~ Poisson(lambda / p)
X | N,p ~ Gamma(shape=N, scale=p), with X=0 exactly when N=0
G | N,p ~ Binomial(N,p)
X and G are independent conditional on N,p
```

X is aggregate provider xG, not an integer count or an extra fractional goal.
One opportunity has mean process contribution p; its measured contribution has
an exponential distribution. Goals add the noisier finishing realization.
Integrating N gives E[X]=E[G]=lambda, Var[X]=2p lambda, Var[G]=lambda and
Cov[X,G]=p lambda, conditional on the team state. Goals marginalize exactly to
Poisson(lambda), so score forecasts and evolving M5 season paths remain coherent
with this observation model. Home and away opportunities are independent given
the joint team state; there is no new shared-Gamma tempo or dispersion tuning.

This is a simplified aggregate process model, not a literal reconstruction of
shots. Provider xG sums calibrated shot probabilities, whereas exponential marks
can exceed one, and the model does not let an individual mark alter finishing
probability once N is given. Variation in average chance quality is represented
by team rate and observation uncertainty, not a separate shot-quality state.
These assumptions make identification possible from match aggregates but limit
what the latent opportunity count means. Assess representation diagnostically;
do not describe inferred N as observed shots or infer individual finishing skill.

## Joint update and uncertainty

By Poisson thinning, missed opportunities M=N−G follow a Poisson distribution
with mean lambda(1−p)/p, independently of G. For positive xG, the joint likelihood
sums `Poisson(G;lambda) Poisson(M;lambda(1−p)/p) Gamma(X;G+M,p)` over M.
Zero xG has exact probability exp(−lambda/p) and requires zero goals; positive
goals with zero xG are outside this first formulation, including own-goal cases.
The audited historical zeros both have zero goals. Missing xG integrates out,
recovering the unchanged Poisson likelihood rather than imputing an xG value.

The sum is evaluated in log space with an adaptive series and a geometric bound
on omitted mass. Its exact derivatives in log lambda use posterior opportunity
count moments. The joint daily Laplace update retains all state covariance and
uses a positive-definite search metric if local likelihood curvature is negative.
The posterior itself must have a positive-definite Hessian. This is approximate
Bayesian filtering, not exact long-history inference or a fixed goals/xG blend.

A finite prior assigns equal mass to p = 0.1, 0.2 and 0.35, spanning conditional
xG variance from 0.2 to 0.7 times mean goals. Chronological joint likelihood
updates the weights; they propagate to forecasts and season paths. This coarse
noise prior is an explicit approximation, not continuous parameter uncertainty.
Dynamics use the existing M5 Poisson corner (Quality retention 0.85, innovation
0.09; Tilt retention 0.5, innovation 0.07), without reopening its grid.

## Information boundary and evaluation contract

Only reconciled Understat observations attached to training results enter the
filter. Historical next-day availability is assumed, not proven by a current
source download. Records marked later than the daily result update are skipped;
the filter does not retrofit delayed observations. Missing recent xG therefore
causes goals-only updates. Target-match xG cannot enter a pre-match prediction.
Processed xG used through configuration must match its pinned SHA-256.

Compare unchanged M2, the original M5 Poisson ensemble, the centered fixed-dynamics
goals-only control and M7 on identical forecast fixtures and dates. Use 2023/24,
2024/25 and 2025/26 as historical development evidence, not fresh holdouts.
Report proper outcome/score loss, calibration, opening-season and promoted-team
slices, adaptation/state interpretation and complementary errors. Include a
separately labeled high-information condition, with no operational claim. Check
likelihood normalization/derivatives, a small sampled posterior, and direct score
probabilities against evolving simulation. Freeze this formulation before those
comparisons; failures trigger an identification/representation diagnosis rather
than tuning lineup heuristics or a broad dynamics search.
