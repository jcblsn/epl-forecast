# Team-observation information value

The first chronological residual test does not establish a stable incremental
forecast gain from individual shots or SOT observations beyond the M7-member
state. Retain M7 as the sensor-fusion parent. Do not add independent shot/SOT
likelihoods on this evidence. This does not rule out information in pooled season
summaries for cross-division initialization, or in other specified observation
models; those require their own matched tests.

## Design and evidence

The retained run is `runs/information-value-v1`, launched from `4cc1131`.
It uses the initial immutable research-ready manifest, both leagues from 2014/15
through 2025/26, and eleven chronological evaluation seasons after the initial
training season. It produced 61,824 source/target observations, 636,328 diagnostic
predictions and 177 matched sensor comparisons.

At each source match, the existing fixed p=0.2 M7 member supplies team/opponent
log-rate means and variances from strictly earlier results and xG. Championship
uses the goals-only marginal with the same dynamics. The source match's goals,
xG, shots and SOT are candidate new observations. Targets are the team's own goals
one, three or six team matches later within that season. Fixture and calendar-gap
controls use retrospectively known schedules. All candidate sensor subsets share
complete cases; residualization and pooled regression fit only earlier seasons
with matured targets. Retrieval timestamps and hashes remain distinct from the
assumed next-day availability of historical observations.

The outcome is noisy future log1p-goals. Squared errors and Gaussian proxy
predictive intervals are diagnostic quantities, not match-score NLL or latent-state
credible intervals. Headlines resample whole seasons. These development data have
been inspected previously; there is no new untouched holdout claim.

## Incremental forecast information

Next-team-match MSE differences versus the state-only diagnostic are below.
Negative means improvement. Intervals are paired 95% season-bootstrap intervals;
all seven cross zero. The same is true of every individual-sensor comparison at
lags three and six. Selected season win counts illustrate the instability rather
than providing a separate significance test.

| League | New sensor | MSE difference | 95% interval | Seasons improved / 11 |
| --- | --- | ---: | --- | ---: |
| PL | Goals | 0.000011 | [-0.000168, 0.000169] | 5 |
| PL | xG | -0.000043 | [-0.000293, 0.000200] | 6 |
| PL | Shots | -0.000251 | [-0.000598, 0.000075] | 6 |
| PL | SOT | -0.000308 | [-0.000808, 0.000260] | 8 |
| Championship | Goals | 0.000035 | [-0.000028, 0.000111] | 5 |
| Championship | Shots | -0.000159 | [-0.000443, 0.000166] | 8 |
| Championship | SOT | 0.000058 | [-0.000052, 0.000171] | 4 |

In PL, adding shots to goals+xG changes MSE by -0.000152
[-0.000379, 0.000077]; adding SOT changes it by -0.000167
[-0.000601, 0.000316]. Neither establishes complementarity. In Championship,
adding SOT to goals+shots changes MSE by +0.000119, with an exploratory interval
[0.000001, 0.000306]. That isolated adverse result is one of many comparisons,
not grounds for a universal claim that SOT is harmful.

## Dependence, persistence and uncertainty

Residual shot/SOT correlation in training before 2025/26 is about 0.589 in each
league. PL xG correlates 0.575 with residual shots and 0.590 with residual SOT.
They cannot defensibly be treated as independent measurements just because they
have different labels. Full matrices and season/team stability are in the report.

Shot residual persistence is modest but nonzero: correlations at retained-match
lags 1/3/6 are 0.056/0.042/0.041 in PL and 0.071/0.067/0.073 in Championship.
Goals and xG residual persistence is much weaker. Persistent shot volume therefore
remains a candidate for pooled transition summaries, but persistence alone does
not demonstrate residual scoring information.

From identical pre-match priors in 2025/26, a single goals update leaves mean
latent log-rate variance at 97.32% of its prior value in PL; goals+xG leaves
92.81%. Championship goals leave 96.17%. These are Laplace posterior quantities
for joint match rates, including league and opponent uncertainty. Shrinkage is
not itself proof of calibrated inference or predictive benefit. No shot/SOT
posterior precision is asserted without an admitted likelihood.

A separate known Gaussian-state check gives 90.065% coverage for nominal 90%
intervals with the correct correlated sensor noise. Incorrect independence gives
65.845% while claiming substantially smaller posterior variance. This validates
the dependence-accounting diagnostic, not a football likelihood.

## Retention and reproduction

Local evidence SHA-256:

- `manifest.json`: `e95dda511de612cb4e8e6e107ebaae9c5937201ca0008e5acbc67afbcddd2cce`
- `observations.json`: `876101296029d14bf2f1c1160a922b3b136169b6bd936a16f34e1686b93e071c`
- `report.json`: `b8cc257a43c7694d0bf37e27a67c816a82c47ac90dc73f255818561e43c2dfa9`
- `predictions.json`: `16bc1a75264b9006874602c00642a93aa0860939af340207419686df4f48f4cc`

```sh
OPENBLAS_NUM_THREADS=1 uv run --locked --all-extras python scripts/evaluate_information_value.py \
  --manifest runs/research-ready-v1-initial/manifest.json \
  --output runs/information-value-reproduction
```

Use a fresh output directory. Provider evidence remains local under its existing
terms. Numerical and chronological checks currently pass in the project suite.
