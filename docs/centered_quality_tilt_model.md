# Centered Quality/Tilt state

`CenteredQualityTiltFilter` is the forecast-equivalent M5 parent for M7. Inference
stores an identifiable scoring level and orthonormal team Tilt contrasts. The
existing M5/M6 implementations and M2 benchmark are unchanged.

For the n registered teams, let m be average population Tilt and H the
(n−1)-by-n Helmert contrast matrix. Replace league level l and team Tilts t by

```
L = l + 2m
c = H t
centered team Tilt = Hᵀ c
```

Home and away log rates are `L + home + Qh − Qa + Th + Ta` and
`L − Qh + Qa + Th + Ta`. Centered Tilts sum to zero. Their n−1 free contrasts
and L have full column rank over all pairings for n >= 3. Quality retains the
existing population anchor and entry priors. Centering uses all registered clubs,
including inactive clubs, and rebases exactly when a club enters; it does not
silently change the football process when league membership changes.

## Preserve dynamics, not just today's rates

The old l is a random walk, but m mean-reverts. Simply deleting m would change
future forecasts. Retain it explicitly as scoring memory, with no direct loading
in any match observation. Over y years, with Tilt retention r,

```
m_next = r^y m + noise_m
L_next = L + 2(r^y − 1)m + noise_l + 2 noise_m
```

Thus L and memory have correlated innovations. At ordinary r < 1, L and memory
are distinguishable through observations across time; they are not two additive
intercepts in the likelihood. At r = 1 memory has no transition effect for a fixed
population and only preserves entry/population bookkeeping. No data-driven claim
about separate league and common Tilt levels is made in that limiting case.

The implementation transforms the full joint prior, covariance and transition
matrices analytically. It stores n−1 contrasts plus one memory coordinate in the
old n Tilt slots; the last slot is memory, not a team's Tilt. Team summaries
reconstruct centered Tilt and its uncertainty. Model consumers must use the
summary and forecast interfaces instead of interpreting raw state slots as pairs.
Promotion entry priors are applied in their original population coordinates and
then rebased. Forward sampling uses an exact inverse transformation to reuse the
existing evolving M5 path sampler. This is a computation of the same generative
process, including entrant draws and calendar-time changes.

## Verification and limitations

Unit tests check analytic inverses, zero memory observation loading, full-rank
scoring contrasts, daily posterior/evidence equivalence, team entries, new-season
forecasts, nonmutating forecasts, correlated transition innovations and paired
future score draws. The existing sampled-reference command supports `--centered`
for a four-chain M5 posterior transformed to these coordinates and a full-history
comparison including promotion bridges:

```sh
OPENBLAS_NUM_THREADS=1 uv run --extra research python scripts/check_quality_tilt_posterior.py \
  --centered --output runs/m7-centered-reference-reproduction
uv run pytest tests/test_centered_quality_tilt.py tests/test_quality_tilt_reference.py -q
```

A linear transformation preserves the likelihood and the existing Laplace
mode-versus-mean approximation error. Structural identification is not a bias
correction. The short sampled check is not evidence of calibrated long-history
states or season outcomes; those remain empirical questions for M7 evaluation.
