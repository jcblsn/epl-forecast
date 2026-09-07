# M8 process batch

M2 remains the operational benchmark and M7-v1 the retained xG research parent.
M8-v1 is parked: treating
provider xG as realized Poisson scoring intensity produces excessive scoring
variation. The batch retains reusable diagnostics and a restricted promotion-bridge candidate.
Prospective archives and the local collector are verified.

## Representation and chronological evidence

The [pre-implementation proposal](../m8_work_plan.md) separates process packet
mass from scoring probability. Its pooled lognormal scale prior is integrated
with Gaussian quadrature. Goals are downstream Poisson draws; missing xG is
integrated analytically. Forecasts carry full centered-state covariance and
scale uncertainty through evolving future states. No market probabilities enter
states and no M7 constants or dynamics were tuned.

The [chronological evidence](m8/chronological_diagnostics.json) covers identical
1,140 fixtures in 2023/24–2025/26. These are previously inspected development
seasons. Market baselines have outcome probabilities, not score distributions.

| Model | Outcome loss | Score NLL | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| M2 | 0.98039 | 2.98251 | 0.58378 | 0.02055 |
| Centered goals parent | 0.98250 | 2.97448 | 0.58516 | 0.02849 |
| M7-v1 | 0.97827 | 2.97217 | 0.58153 | 0.03598 |
| M8-v1 | 0.98380 | 3.02554 | 0.58421 | 0.03824 |
| Average pre-closing market | 0.96502 | — | 0.57401 | 0.02037 |
| Average closing market | 0.95973 | — | 0.56989 | 0.01809 |

M8 worsens outcome loss and score NLL in both evaluation periods. Its paired
outcome-loss difference versus M7 is +0.00553 (calendar-week bootstrap 95%
interval [0.00278, 0.00828]). Opening-five loss is 0.94776 versus 0.93488; promoted
match loss is 0.90655 versus 0.89435. The linked
machine-readable evidence also contains Brier, fixed-bin calibration, promoted
and opening slices, and paired calendar-week bootstrap comparisons.

## State and observation checks

Across 9,120 team-match observations, conditional Poisson scoring predicts a
32.44% scoreless frequency versus 27.03% observed, and a 9.42% frequency of four
or more goals versus 6.39% observed. Conditional Pearson dispersion is 0.789.
The issue is excess modeled variation, not simply a mean-rate bias. Realized xG
is used only for this diagnostic, never as target information in forecasts.

The [known-state experiments](m8/state_diagnostics.json) use 30 independent
replicates per regime, with full, half and absent xG. Under the M8 generative
model, full-xG 90% rate-interval coverage is 89.61% (replicate SE 0.65 percentage
points). M7 covers 86.63%. Under added multiplicative provider noise (CV 0.5),
M8 coverage falls to 85.62%, versus 88.30% without xG. The report separately
records centered Quality/Tilt coverage, rate MSE and adaptation after a +0.35
Quality shock. These results support implementation under the assumed model,
not calibrated state uncertainty on historical football data.

Two conditional sampled references cover opening and midseason regimes:
[opening](m8/reference_opening.json), [midseason](m8/reference_midseason.json).
Each uses four chains, 600 warmup iterations and 800 retained draws per chain.
There are no divergences; maximum R-hat is below 1.002 and minimum ESS exceeds
1,900. Maximum mean discrepancies are 0.327 and 0.349 reference SD; median
filter/reference SD ratios are 0.991 and 0.956. These are fresh-population,
fixed-scale checks, not full-history or scale-mixture calibration.

Extreme synthetic line-search proposals exposed a numerical series limit.
M8 now uses an equivalent finite positive-jump sum for missing xG and a scaled
Bessel density for observed mass. The shared Laplace line search backtracks
unresolvable numerical proposals and allows floating-point rounding at the
objective floor. M7's likelihood, noise grid and series constants remain fixed;
its numerical cap now raises a typed exception. Recomputed chronological home
probabilities differ from the original successful run by less than 4e-9 across
all models. Failed diagnostic directories remain separate from retained runs.

The [pre-match predictive checks](m8/predictive_diagnostics.json) cover the same
1,140 fixtures with 2,000 joint process/goal draws per match. M8 xG central-90%
coverage is 86.49%, versus 91.23% for M7. M8 predicts 27.53% scoreless team
performances versus 23.20% observed; M7 predicts 22.81%. The M8 scale quadrature
collapses onto q=0.15555. Nine-node checks instead select q=0.17474 and change
sampled match probabilities by up to 0.00567. This is numerical under-resolution
of a concentrated scale posterior, not evidence of negligible scale uncertainty.
Do not retune the grid to rescue the failed observation assumption.

## Championship initialization

The [raw-field audit](m8/process_fields.json) covers the pinned 16-season source.
There is a clear 2013/14 change in the relationship between shots and shots on
target. The [provider field notes](https://football-data.co.uk/notes.txt) define
the count labels but do not establish consistent historical coding. Restrict the
process experiment to 2013/14 onward; exclude missing or internally inconsistent
rows. Do not interpret historical capture time as next-day publication evidence.

The [bridge test](m8/bridge_diagnostic.json) maps division/home-adjusted
Championship shot summaries into promoted-team process priors with a pooled
errors-in-variables regression. It carries source sampling variance, coefficient
uncertainty and cross-division residual variation, with a prespecified minimum
prior SD of 0.25. It uses only completed earlier cohorts at each preseason cutoff.
There is no arbitrary blend of goals and shots in the observation likelihood.

Across nine promoted teams in 2023/24–2025/26, squared error against noisy
first-ten PL xG summaries is 0.07662 versus 0.08788 for the frozen population
bridge. Proxy predictive NLL is 0.14948 versus 0.43786, and 90% proxy interval
coverage is 88.89% versus 72.22%. These summaries include target observation
variance and are not latent-state coverage. This is useful evidence for a
restricted process bridge, not a validated change to live promoted priors.
Retain the current operational bridge while carrying this candidate forward.

## Player-process foundation

The [second-player proposal](../player_process_model.md) defines a pooled,
role-aware attacking-process layer with persistent club/system defense and an
actual-minutes versus forecast-minutes comparison. The [identity audit](m8/player_identity.json)
links 760 sampled appearances and keeps 107 unresolved; 166 lack FPL coverage.
Role/provider distinctions and source hashes are retained. No operational player
layer relies on these incomplete links. Because M8 did not settle into an adequate
team observation model, its conditional player-extension experiment was not
triggered; no player-process oracle gain is claimed.

## Prospective retention and operation

The [prospective manifest](m8/prospective_manifest.json) verifies fresh M2/M5/M6/M7/M8
exports, each with 350 pre-kickoff forecasts and 2,000 season paths fixing the
30 captured results. The compressed bundle retains 719 files: model exports,
raw snapshots, timestamped player histories and attempt records. Hash checks,
pre-kickoff eligibility, table constraints and direct-versus-simulated frequencies
pass. Across models, 99.52–99.81% of outcome frequencies are within three Monte
Carlo standard errors. This verifies the forecasts' implementation and timing,
not predictive calibration. No new matches have matured for prospective scoring.

The local half-hourly LaunchAgent is installed and verified. A separate scheduled
invocation captured a new snapshot and correctly skipped duplicate forecasts
when the meaningful information fingerprint was unchanged. Attempts and raw
snapshots remain immutable; model failures are isolated; changed fixture/results
or availability signals trigger new forecasts. Existing M7-batch prospective
sources and exports still match their retained hashes. The collector depends on
an awake local computer and network, and current-season xG missing from the
frozen historical pin is integrated as missing. No frontend or notification
project was added.

## Verification and decision

[Verification](m8/verification.json) records 205 passing tests, the final capture
tests, Ruff, retained source pins, recomputed metrics, and chronological cutoffs.
M2 parameters and predictions are unchanged. M7 research artifacts, observation
constants and dynamics remain frozen; its only implementation change is the
numerical exception handling described above. The M6 player coefficients,
lineup assumptions and model architecture are unchanged.

Park M8-v1. Retain M7 as the research parent, M2 operationally, and the restricted
shot bridge as an initialization candidate requiring stronger forecast evidence.
Carry forward the tested diagnostics and player-process foundation. Do not
elaborate the rejected observation model or interpret an under-resolved scale
posterior as calibrated uncertainty.

To reproduce in fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 uv run epl-forecast evaluate \
  --config configs/process_quality_tilt.toml --split validation --output runs/m8-validation-new
OPENBLAS_NUM_THREADS=1 uv run epl-forecast evaluate \
  --config configs/process_quality_tilt.toml --split holdout --output runs/m8-holdout-new
OPENBLAS_NUM_THREADS=1 uv run python scripts/diagnose_xg.py \
  --evaluations runs/m8-validation-new runs/m8-holdout-new \
  --config configs/process_quality_tilt.toml --focus-model M8-process-v1 \
  --include-markets --skip-oracle --output runs/m8-comparison-new
OPENBLAS_NUM_THREADS=1 uv run python scripts/diagnose_process.py \
  --replicates 30 --bridge --output runs/m8-state-new
OPENBLAS_NUM_THREADS=1 uv run python scripts/diagnose_process.py \
  --replicates 0 --predictive --start 2023-08-01 --end 2026-07-01 \
  --output runs/m8-predictive-new
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --xg data/processed/understat/matches.json --process-scale 0.25 \
  --start 2024-08-01 --end 2024-11-01 --output runs/m8-reference-opening-new
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --xg data/processed/understat/matches.json --process-scale 0.25 \
  --start 2025-01-01 --end 2025-04-01 --output runs/m8-reference-midseason-new
uv run python scripts/audit_process_fields.py --output runs/m8-fields-new.json
uv run python scripts/audit_player_process.py --output runs/m8-identities-new.json
OPENBLAS_NUM_THREADS=1 uv run --extra research pytest -q
uv run ruff check .
```
