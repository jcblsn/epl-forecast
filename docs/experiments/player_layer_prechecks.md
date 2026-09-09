# Pre-registered player checks

Recorded before fitting or scoring any candidate in the standalone player-process
batch, so that the named cases cannot become tuning targets. Each entry states what
a competent attacking-process representation should show and what would count as a
failure. None of these are objectives; they are falsification cases.

## Named cases

| Player | Component under test | Expected if the representation works | Failure signature |
| --- | --- | --- | --- |
| Erling Haaland | Shooting (xG, shots) | Shooting component far above the FWD population with narrow intervals; the shooting estimate must not depend on being told Manchester City score a lot. | Shooting estimate near the pooled forward mean, or collapsing when the club environment term is removed. |
| Mohamed Salah | Shooting and creation | Elevated on both components; creation clearly separated from shooting rather than implied by it. | Only one component moves, or the two are indistinguishable. |
| Bukayo Saka | Creation (xA, key passes) | Creation component clearly above the population; shooting elevated but by less than Haaland. | Creation indistinguishable from the pooled midfield/forward mean. |
| Dominic Solanke | Cross-club continuity | Estimate survives the Bournemouth to Tottenham move; the post-move prediction should not be dominated by the new club's environment. | Estimate resets to the pooled prior after the move, or tracks only the new club. |

## Controls, recorded with the named cases

- A low-history control: a player with under 300 retained process minutes before the
  cutoff must receive visibly wider intervals than an ever-present starter.
- A team-context control: a player with strong raw per-90 numbers at a strong club
  whose within-team opportunity share is ordinary. Context adjustment should move this
  player down relative to raw rates; raw-rate candidates should not.
- A goalkeeper and a centre-back: attacking components must be near zero with the
  role pooling carrying the estimate, not spuriously large.

## Rules

- No hyperparameter, feature set or shrinkage strength may be changed after looking at
  where these players rank. Changes may only follow a stated defect in the data
  semantics, the chronology, or the estimator, recorded in the report.
- A plausible leaderboard is not evidence. Only the chronological and post-transfer
  scores decide whether a representation is retained.
