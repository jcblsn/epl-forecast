# Championship playoff conditioning

## Decision

The bracket is played out on the same latent team states that produced each
simulated regular-season path. The previous behaviour resampled every playoff tie
from the common forecast distribution, which threw away the strength that put a club
in the playoffs on that path and put the league-wide marginal back in its place. The
correction is retained; the old behaviour stays available as `playoff_conditioning="marginal"`
so the difference can be measured rather than asserted.

## The correction is confined to the bracket

A path's regular season is complete before the playoffs begin, so nothing about the
table can depend on how the bracket is sampled. That is a falsifiable claim, and it
is what a matched run checks: identical model, teams, fixtures, sanctions, seed and
50,000 paths, with only the conditioning switched.

| Quantity | Result |
| --- | --- |
| Largest points PMF difference over all clubs | 0.0 |
| Largest rank PMF difference over all clubs | 0.0 |
| Largest mean-points difference | 0.0 |
| Promotion mass, marginal | 3.000000 |
| Promotion mass, path-conditioned | 3.000000 |
| Mean absolute promotion change | 0.00462 |
| Largest single promotion change | 0.0204 |
| Clubs flagged above the 0.05 investigation threshold | none |

Points and rank distributions are identical to the last decimal, which is the
intended invariance. Promotion mass is conserved at three places. No club moves far
enough to warrant investigation.

## Direction of the change

| Club | Marginal promotion | Path-conditioned | Change | Playoff qualification |
| --- | ---: | ---: | ---: | ---: |
| Southampton | 0.4359 | 0.4155 | −0.0204 | 0.4631 |
| Middlesbrough | 0.3948 | 0.3782 | −0.0166 | 0.4620 |
| Lincoln City | 0.0506 | 0.0630 | +0.0125 | 0.1391 |
| Burnley | 0.2859 | 0.2784 | −0.0075 | 0.4343 |
| Millwall | 0.2283 | 0.2237 | −0.0047 | 0.4347 |
| Queens Park Rangers | 0.0415 | 0.0459 | +0.0044 | 0.1954 |

Mass moves from the strong qualifiers to the weak ones, which is the opposite of the
naive expectation and the right answer. Reaching the playoffs is evidence about the
path, and what that evidence says depends on the club. A club whose marginal state is
weak reaches the playoffs only on paths where it was drawn strong, so conditioning on
the path makes it stronger in the bracket than the marginal would. A club strong
enough that a good path usually ends in automatic promotion arrives at the playoffs
having been drawn worse than average, so conditioning makes it weaker. Resampling
from the marginal erased that selection in both directions.

The effect is small at this point in the season, when six played matches leave the
table mostly unresolved and qualification carries little information about the draw.
It should grow as paths separate.

## Reproducing

`runs/playoff-conditioning-v1`, Championship 2026/27, information cutoff
2026-09-10T17:12Z, M7-xg-v1, seed 20260910, 50,000 paths, with Southampton's
four-point sanction in force. The retained
[validation](playoff_conditioning/validation.json) and
[per-club table](playoff_conditioning/playoff_conditioning.csv) record every club,
not only the movers.

```sh
OPENBLAS_NUM_THREADS=1 uv run python scripts/validate_playoff_conditioning.py \
  --cutoff <ISO-timestamp> --output runs/playoff-conditioning
```
