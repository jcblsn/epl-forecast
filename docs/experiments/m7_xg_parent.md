# M7 xG-informed parent batch

September 6, 2026. In progress; M2 remains unchanged. The full completion scope
is in [the work plan](../m7_work_plan.md); research decisions follow
[the research principles](../research_principles.md).

## Historical source audit

The [Understat league page](https://understat.com/league/EPL/2024) now requests
`getLeagueData/EPL/{year}` using `X-Requested-With: XMLHttpRequest`. The adapter
uses that same public website contract. Responses may contain gzip bytes; hashes
cover the original bytes, and parsing handles compression explicitly. This is an
undocumented external dependency. The manifest pins 12 responses under
`data/raw/understat/`; changed upstream bytes cannot silently replace them.
Keep these local raw files when moving the research workspace: if the provider
revises its response, a manifest alone cannot recover the original bytes.

The [machine-readable audit](m7/understat_audit.json) covers 4,560 matches,
380 per season from 2014/15 through 2025/26. All home/away team identities and
scores reconcile to the hashed canonical Football-Data table. Twenty-six
2015/16–2016/17 timestamps are midnight on the day after the canonical date.
The adapter uses an explicit correction registry bound to source hash, provider
match ID, original timestamp, canonical fixture ID and canonical date. It retains
the original timestamp and lists every correction in the audit. The cause of
these source timestamps is not established; no blanket timezone shift or fuzzy
fixture matching is applied. Other date mismatches fail the audit.

Observations retain Understat's match `xG`, including penalties, separately from
`npxG` and FPL xG. Zero is valid. The current snapshot is retrospective: next-day
availability is a historical evaluation assumption, not evidence of original
publication time or freedom from provider revisions. Source retrieval timestamps
are retained in the pinned manifest. Target-match realized xG must never enter a
deployable pre-match forecast. Provider season-level player summaries are present
but do not establish stable player-match coverage; that audit remains pending.

Reproduce the source audit and adapter checks:

```sh
uv run python scripts/audit_understat.py
uv run pytest tests/test_understat.py tests/test_data.py -q
```

Eleven adapter tests cover gzip, checksums, cache reuse, drift rejection, aliases,
zero/nonfinite/negative xG, dates, scores, duplicate/unfinished matches and the
exact-source correction boundary. The audit refuses to publish normalized
modeling inputs if any completed-season fixture remains unresolved.

## Centered research parent

The [centered state implementation](../centered_quality_tilt_model.md) absorbs
common Tilt into league scoring and stores n−1 free team Tilt contrasts. It
retains the common component as transition-only mean-reverting scoring memory;
removing that memory would change M5's future distribution. Match observations
have exactly zero direct memory loading, and scoring level/contrasts have full
column rank. Team entry rebases the state without changing priors or forecasts.

The [reference evidence](m7/centered_reference.json) uses four chains with 600
warmup and 800 retained draws per chain, no divergences, maximum R-hat 1.0010
and minimum effective sample size 2,215. Transformed sampled rates differ by at
most 1.11e-15. The centered filter preserves the original posterior approximation:
its maximum mean discrepancy from the sampled posterior remains 0.597 reference
standard deviations. No moment correction has been added or claimed.

The full retained history contains 14,912 PL/Championship results, 41 PL team
states and 45 promotion-bridge entries. Original versus centered mean differences
are at most 9.08e-10, covariance differences 2.09e-12, and log-evidence difference
5.63e-8. Seven-day-ahead rate mean/covariance differences are below 5.29e-11 and
7.22e-14. All 10,000 paired future match score draws agree. Separate tests also
exercise unknown next-season entrants and multiple evolving forecast dates.
Twenty-seven centered, sampled-reference, Quality/Tilt and dynamic tests pass.
These are equivalence checks, not evidence of calibrated season uncertainty.

## Probabilistic xG parent and first comparison

M7 now implements the [joint opportunity observation model](../xg_model.md).
Latent opportunities jointly generate Gamma aggregate xG and Binomial goals;
marginal goals remain Poisson. Missing xG recovers the original goal likelihood,
zero xG has an explicit atom, and posterior opportunity moments determine state
updates. Bayesian weights over three observation-noise specifications propagate
into the centered state and evolving season paths. Inputs are checksum-pinned
through `configs/xg_quality_tilt.toml`. No lineup heuristics or M2 parameters changed.

The [M7 sampled reference](m7/xg_reference.json) uses the exact configured dynamics
on the same 90-match fresh-population subset. Four chains have no divergences,
maximum R-hat 1.0010 and minimum effective sample size 2,114. Maximum posterior
mean discrepancy is 0.2585 sampled standard deviations; median filter/reference
SD ratio is 0.9920. The maximum sampled likelihood series tail bound is 6.45e-91.
This is conditional on p=0.2 and fixed dynamics, not a noise-mixture or long-history
calibration claim.

The [initial chronological summary](m7/chronological_summary.json) preserves the
1,140-fixture comparison and input/output hashes. Over 2023/24–2024/25, M7 outcome
loss is 0.95285 versus M5's 0.95692, and score loss is 3.01052 versus 3.01556.
In 2025/26, outcome loss is 1.02912 versus M5's 1.03366, but score loss is slightly
worse (2.89547 versus 2.89232). M2 has better 2025/26 outcome loss (1.02649).
The original M5 Poisson ensemble and centered fixed control agree to reported
precision; its existing dynamics weights already concentrate on that corner.
These comparisons do not establish operational promotion. Slices, calibration,
complementarity, high-information diagnostics and state interpretation follow.

Reproduce with fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 uv run epl-forecast evaluate \
  --config configs/xg_quality_tilt.toml --split validation --output runs/m7-validation-reproduction
OPENBLAS_NUM_THREADS=1 uv run epl-forecast evaluate \
  --config configs/xg_quality_tilt.toml --split holdout --output runs/m7-holdout-reproduction
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --xg data/processed/understat/matches.json --output runs/m7-reference-reproduction
```

The CLI split names are retained for compatibility; all these previously inspected
seasons are historical development evidence. The full suite passed 159 tests at
the implementation checkpoint. Tests cover marginal normalization, joint moments,
analytical derivatives, zero/missing xG, checksums, cutoff isolation, batch versus
incremental filtering, sampled likelihood agreement and future-path probabilities.

## Remaining work

High-information and slice/calibration/state diagnostics, full evolving-season
validation, player-source follow-up and prospective archive refresh/verification
remain required. The current comparisons do not complete the batch audit.
