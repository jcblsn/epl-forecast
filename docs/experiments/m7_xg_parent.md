# M7 xG-informed Bayesian parent

September 6–7, 2026. M7 is the implemented research parent; M2 remains the unchanged
operational benchmark. The first team xG formulation improves aggregate historical
loss and process-state estimates, but does not improve opening/promoted slices,
and its calibration and approximation limits preclude operational promotion.

## State and observation model

[Research principles](../research_principles.md) separate useful information,
adequate representation and sufficient operational evidence. M5/M6 remain the
research lineage; failure of an implementation is not rejection of its information
channel. No player Tilt, lineup-heuristic tuning, broad dynamics grid, market/news
layer, scheduler or frontend batch was added.

The [centered parent](../centered_quality_tilt_model.md) absorbs common Tilt into
scoring level, with n−1 free team Tilt contrasts. It retains transition-only
mean-reverting scoring memory to preserve M5's unequal league/Tilt dynamics.
Observed match rates have zero direct memory loading. Full-history equivalence
covers 14,912 PL/Championship results, 41 registered PL teams and 45 promotion
entries: maximum mean difference 9.08e-10, covariance difference 2.09e-12, and
zero discrepancies among 10,000 paired future match score draws.
[Sampled-reference evidence](m7/centered_reference.json) confirms transformed
rates to 1.11e-15. A coordinate change preserves the Laplace mode/mean bias;
no moment-correction patch was promoted.

The [M7 observation model](../xg_model.md) jointly generates aggregate xG and goals
from latent opportunities. Marginal goals remain Poisson; missing xG integrates
out to the goals-only likelihood, and zero xG has an explicit probability mass.
Chronological joint evidence weights a finite prior over observation noise, with
frozen M5 dynamics. Full state covariance and these weights propagate through
match forecasts and evolving season paths. The model's aggregate opportunities
are not literal shots or identifiable individual finishing/goalkeeping effects.

The [M7 sampled check](m7/xg_reference.json) uses configured dynamics and p=0.2 on
90 matches: four chains, no divergences, maximum R-hat 1.0010, minimum ESS 2,114,
maximum mean discrepancy 0.2585 reference SD and median filter/reference SD ratio
0.9920. This validates a small conditional approximation, not full-history or
noise-mixture calibration.

## Historical information and provider semantics

The [pinned Understat audit](m7/understat_audit.json) reconciles all 4,560 EPL matches
from 2014/15–2025/26 against canonical team identities and scores. Twenty-six
midnight timestamps in 2015/16–2016/17 use explicit, hash-bound canonical-date
corrections; original timestamps remain retained. The public website's
`getLeagueData/EPL/{year}` AJAX responses are cached and pinned. Changed upstream
bytes cannot silently replace them. Preserve `data/raw/understat/` when moving
the workspace; a manifest alone cannot restore an upstream revision.

These are retrospective observations. Next-day availability is assumed, not
established by today's download. Late-marked records are skipped, and target xG
never enters deployable pre-match forecasts. Understat and FPL definitions remain
separate, as do Understat league-match xG and additive player/shot xG.

## Chronological and diagnostic evidence

The [chronological summary](m7/chronological_summary.json) and
[diagnostics](m7/diagnostics.json) cover identical forecast dates and 1,140 fixtures
in 2023/24–2025/26. These previously inspected seasons are development evidence.
Lower loss is better; ECE is descriptive, using fixed bins.

| Model | Outcome loss | Score loss | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| Unchanged M2 | 0.98039 | 2.98251 | 0.58378 | 0.02055 |
| M5 Poisson | 0.98250 | 2.97448 | 0.58516 | 0.02849 |
| Centered goals-only control | 0.98250 | 2.97448 | 0.58516 | 0.02849 |
| M7 xG | 0.97827 | 2.97217 | 0.58153 | 0.03598 |

M7's paired outcome-loss difference versus the centered control is −0.00423;
a 2,000-replicate calendar-week bootstrap gives a 95% interval [−0.01070, 0.00185].
Its probability-error correlation with the control is 0.9964, so complementarity
is modest. Outcome loss improves in both evaluation periods, but 2025/26 score
loss worsens slightly, and M2 has lower 2025/26 outcome loss.

M7 does not improve the first-five-appearance slice (151 matches: 0.93488 versus
0.93274) or promoted-team matches (324: 0.89435 versus 0.89345). The 43 promoted
opening matches are also worse. Initial promoted priors still use the frozen
Championship bridge, without Championship xG. This remains a limitation rather
than a reason to tune lineup constants or discard process observations.

Pre-match xG mean squared error falls from 0.71446 to 0.68438, and mean rate bias
from −0.09989 to −0.00945. Mean log-rate variance falls from 0.02703 to 0.01826;
narrower uncertainty alone is not evidence of calibration. In 40 known-state
synthetic replicates with a +0.35 Quality shock, first-three-post-change log-rate
MSE falls from 0.32697 to 0.20689; the paired improvement is −0.12007 (replicate
SE 0.02557). This supports tracking under the assumed observation model, not a
claim of historical transfer adaptation or calibrated real-world state intervals.

A separately labeled, nondeployable oracle conditions on realized target xG and
excludes target goals. It reweights state and noise uncertainty, giving outcome
loss 0.88440 and score loss 2.72761; opening loss is 0.85046. This confirms useful
match-process information, not that realized target xG can be recovered before
kickoff. The oracle's gains are not an operational forecast result.

## Player foundation and prospective evidence

The [player-source audit](m7/understat_players.json) pins 36 opening/midpoint/final
fixtures across 12 seasons. It finds 721 player IDs, 201 recurring across seasons,
no sampled name conflicts, and reconciled roster/shot identities, counts and goals
including own-goal semantics. Minutes, starter positions, xG, xA, key passes,
xGChain and xGBuildup are available. This is a deterministic sample, not exhaustive
player-match coverage or a completed FPL identity join.

In 28 of 72 sampled team observations, league-match xG differs from additive
roster/shot xG. Retain this distinction; do not force player contributions to sum
to the current team observation. Some differences are consistent with adjustment
for dependent chances, but this audit does not establish the provider's rule.
Substitute roles are recorded only as `Sub`. The next player formulation should
therefore use strongly pooled attacking process contributions with explicit role
and provider mappings, leaving persistent club/system effects in team state.
No defensive or Tilt player effects are justified by this audit.

A fresh snapshot and 654 player-history responses produced new M5/M6 archives;
M7 was also archived. Each contains 350 forecasts before the first captured
kickoff on September 12. M5/M6 each use 2,000 evolving season paths; M7 uses 10,000.
All fix the 30 captured results. Archive/input hashes, lineup minute totals,
position/points constraints and direct-versus-simulated match frequencies pass.
For M7, mean absolute simulation discrepancy is 0.791 standard errors and 99.90%
of 1,050 outcome frequencies are within three SE. This verifies implementation,
not season calibration. Previous M6 retained evidence also reverified successfully.
The [prospective manifest](m7/prospective_manifest.json) identifies the compressed
bundle retaining all three exports, their snapshot and timestamped player inputs.

## Reproduction and decision

Use fresh output directories. Original source/model commands and assumptions are
in the linked model documents. The final diagnostic command combines saved
chronological predictions, the oracle, synthetic tracking and archive checks:

```sh
uv run python scripts/audit_understat.py --players
OPENBLAS_NUM_THREADS=1 uv run python scripts/diagnose_xg.py \
  --evaluations runs/m7-validation-v1 runs/m7-holdout-v1 \
  --adaptation-replicates 40 \
  --archives runs/m7-prospective-m5 runs/m7-prospective-m6/current runs/m7-prospective-xg \
  --output runs/m7-diagnostics-reproduction
OPENBLAS_NUM_THREADS=1 uv run --extra research pytest -q
uv run ruff check .
```

[Final validation](m7/verification.json) passed 165 tests, Ruff and the diff check.
The M2 implementation/configuration and M6-v1 player/lineup parameters are unchanged.

Retain M7 as the team research parent and M2 operationally. Investigate observation
representation, calibration, promoted information and role-aware player process
statistics next. The evidence supports that bounded continuation; it does not
justify a deployment switch or further tuning of M6-v1's prototype heuristics.
