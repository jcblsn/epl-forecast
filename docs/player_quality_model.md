# M6 player Quality vertical slice

M6 retains dynamic club/system Quality and team Tilt, and jointly fits static
scalar player Quality with the daily goal likelihood. A player's coefficient
is multiplied by their share of observed team minutes. Independent Poisson is
the primary likelihood; shared Gamma tempo remains a constructor ablation.

The initial population hierarchy uses beta ~ Normal(0, 0.6²), with the scale
fixed before evaluation. A full-match player contributes approximately beta/11
to team Quality. Club and player posterior cross-covariances are retained;
regularizing priors resolve the otherwise weak club/roster decomposition.
These coefficients are goals-based conditional associations, not causal player
values. The first implementation keeps player effects static and does not add
player Tilt, individual xG, or transfer valuation.

Forecasts integrate a finite mixture of sampled candidate lineups with the
joint Gaussian posterior. Unseen and anonymous players receive population
uncertainty. Season paths draw persistent player coefficients once, evolve club
states over calendar time, and resample minutes at each fixture. Availability
uses the existing timestamped, expiring squad assumptions.

Historical fitting uses corrected actual minutes only for training matches.
Target-match actual minutes are exposed only through an explicitly requested
oracle score distribution. Deployable candidates use prior appearances or an
explicit timestamped squad snapshot. Historical publication times and opening
season membership remain limitations.

## Inference, summaries and evidence

The ensemble retains the original four independent-Poisson M5 dynamics
specifications and learns their chronological evidence weights with the player
layer present. Full posterior covariance is retained; forecast projection uses
only nonzero design columns, without dropping any contributing covariance.

A probabilistic historical carry-forward option gives players observed at the
previous season's final club a 0.7 membership probability until current-season
appearance evidence replaces it. Players absent from the final 45 days of that
season are excluded. This is a coarse membership prior, not a transfer archive;
unobserved departures can remain in its pool. It never discovers arrivals from
future target-season appearances. Snapshot squads take precedence in live use.

For each future fixture, exports report club Quality projected to kickoff,
expected player contribution and player minutes. `lineup_selection_quality_sd`
is sqrt(E_beta[Var_lineup(w beta)]), including posterior coefficient uncertainty;
`lineup_mean_effect_sd` isolates variation at posterior mean coefficients.
Club/player covariance also enters the full match forecast. The season output
retains match outcome frequencies for direct-probability comparisons.

The [batch report](experiments/m6_player_quality.md) retains the full chronological
comparison, targeted slices, sampled-reference diagnostics, current availability
scenario and prospective archive. Oracle output is explicitly non-deployable.
Known historical absence timestamps remain unavailable and are never invented.

The reference checks one fixed dynamics specification on 60 real matches with
fresh population club priors. It does not validate full-history promotion
uncertainty or eliminate the inherited scoring-level approximation bias.

M2 remains operational. M6 promotion requires separate chronological and
forward evidence; completing the vertical slice does not imply promotion.
