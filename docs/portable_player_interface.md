# Portable attacking traits, interface v1

The frozen interface exports a distribution over shooting and creation, in that
order, measured as Understat xG and xA per 90 minutes. It preserves the long-horizon,
role-shrunk process predictors evaluated in the
[corrected player experiment](experiments/player_layer_corrections.md). Shooting
has stronger transfer evidence; creation is retained with weaker portability
confidence. Neither is a causal player value or a player-defence estimate.

The implementation is `research/portable_players.py`. `PortablePlayerLayer.freeze`
accepts a canonical player ID and an exclusive local-date cutoff. Its immutable
`PortablePlayer` value exposes `sample(paths, generator)` and `as_dict()`; exported
records declare `portable-attacking-traits-v1`. The trait order, units, distribution
parameters and timing policy are part of this contract. No team forecasting model,
team attack environment, target lineup or target minutes enters estimation.

## Distribution and uncertainty

For each trait, keep the existing 240-day half-life, 10-match rate prior and
50-match role-pool prior. With weighted process total T, weighted exposure E,
role-population rate r and empirical process dispersion v, the marginal is

```text
rate ~ Gamma(shape=(T + 10 r) / v, scale=v / (E + 10))
```

Its mean is exactly the existing long-run shrunk process predictor, apart from a
positive numerical floor on a zero role rate. Exposure decays as evidence becomes
stale: the trait regresses to its population prior and retains uncertainty. The
record reports effective matches, appearance count, last-observation staleness,
prior rate, source hashes, source-snapshot fingerprint and configuration.

The two Gamma marginals are conditionally independent in v1. Cross-trait covariance,
shared role-population uncertainty and calibration of these latent-rate intervals
are unestimated and stated explicitly in every export. The standalone experiment's
CRPS and interval-coverage results concern an additional learned chronological
mapping and empirical future-process residual distribution. They are not evidence
that these Gamma latent-rate intervals have that same coverage. Downstream B is
learned separately in the bridge; this interface does not export that player-target
mapping as a universal player rating.

An unknown player receives an uncertain UNK population prior. That is a declared
cold start, not evidence of foreign-league ability. Both traits require a nonzero
eligible process population; before that population exists, export fails explicitly.

## Evidence timing and identity

Use `portable_observation_rows(data)` with a retained research manifest. API
appearances and Understat process records each obey their own availability date.
Retrospective records become eligible after the match date; captured records also
wait until after their provider retrieval date. This is an explicit historical
replay convention, not a claim that later-captured historical data was archived
before those matches. Future payloads, including later Understat evidence for an
already-known API appearance, cannot change an earlier frozen trait.

Unresolved identity, duplicate process linkage, missing process marks and invalid
process values exclude the record from the vector and are counted in the export's
cutoff-population audit. Raw provider rows remain untouched. Source hashes identify
personal process evidence; the snapshot fingerprint also identifies the population,
appearance exposure, role and identity evidence. Team identity and canonical player
IDs survive club changes.

## Consumption contract

The known-minutes bridge must compute both target and recent-reference personnel
from the same cutoff's frozen player distributions, then subtract roster vectors
at application time. Reuse each player's draw on both sides of that subtraction:
a normal repeat lineup then cancels exactly, including its uncertainty. Actual
target minutes are an oracle input for the bridge and do not enter this interface.
Keep shooting and creation separate until fitting the chronological mapping B.

The layer caches one cutoff population at a time. Group export or bridge requests
by cutoff to avoid reconstructing a population for each player.

A retained export can be produced with:

```sh
uv run --all-extras python scripts/freeze_portable_players.py \
  --manifest runs/research-ready-v2-player-layer/manifest.json \
  --output runs/portable-players-v1 \
  --cutoff 2026-06-01 --player-id p1100 --player-id p1460
```

Without `--player-id`, export the IDs present in eligible appearance evidence at the
cutoff. Explicitly requested unknown IDs receive the cold-start prior. A new,
nonempty output directory is required so retained exports cannot be overwritten.
