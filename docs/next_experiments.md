# Research queue

The forecasting harness is sufficient for the next round of model development.
M2 is the current score model; keep M3 as a benchmark and deprioritize further Elo
tuning. The E001/E002 reports retain their original methodology and results.

## Working loop

Use `idea → small implementation → rolling CV → inspect errors → iterate`.
All historical seasons can contribute evidence. When reporting a hyperparameter
selection strategy, choose parameters using only earlier seasons, then evaluate
on the next season. Keep daily result cutoffs, per-match predictions, per-season
proper scores, calibration and matched market comparisons.

An exploratory candidate needs a short result table and a useful conclusion.
Frozen protocols, fixed minimum improvements, confidence-interval acceptance
gates and fresh-directory reconstruction are optional. Use robust ablations and
uncertainty estimates for promising comparisons. Similar standalone performance
with different errors can make a candidate useful in an ensemble.

Timestamped live predictions from September 2026 onward are the forward test.
Archive before kickoff, retain every run, and choose a consistent forecast horizon
when scoring the stream. Collection of a source does not commit us to modeling it.

## Priorities

| Order | Work | Practical next step |
| --- | --- | --- |
| A | Live collection | Implemented: timestamp FPL players/availability, schedule/results and Football-Data fixtures/odds and current E0/E1 results. Keep capturing. |
| B | Current forecast | Implemented: M2 match probabilities, score matrices, strengths, current-season simulation and static output. Archive each refresh. |
| C | M2 tuning | Completed the 30-setting search with daily refits and selection from earlier seasons. Defaults sit in the best region; retain them. See the [short result](experiments/m2_tuning.md). |
| D | Promotion continuity | Use the Championship history to estimate promoted-team priors or a division-aware strength model. Inspect promoted clubs separately. The first live forecast makes this weakness visible. |
| E | Lagged shots | Test prior-date shots and shots-on-target for/against from the cached PL files. No new source is needed. |
| F | Goal distribution | Small Dixon–Coles comparison; inspect H/D/A loss, score NLL and low-score calibration. Consider alternatives only if useful. |
| G | Dynamic attack/defense | Explore evolving team states and parameter uncertainty, then sample that uncertainty in season simulation. This matters more than additional table-rule edge cases. |
| H | Player/squad layer | Use the accumulating FPL snapshots to audit minutes, squad continuity and point-in-time availability. |
| I | xG | Audit viable free sources and definitions before making xG a dependency. |
| J | Market assistance | Compare structural, market and combined forecasts at disclosed information horizons; test incremental information chronologically. |

European qualification remains conditional on cup results and allocated slots.
Unconditional qualification needs additional competition models; retain honest
position probabilities in the meantime.
