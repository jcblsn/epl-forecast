# Next experiments after E002

The first milestone works. M2 is a provisional baseline, not the end of model
selection. [E002](experiments/E002.md) implemented the first Elo/draw comparison;
the candidate did not meet its promotion gate and remains a benchmark. Keep each
experiment's frozen results and record rejections as well as gains. The 2025/26
holdout is now consumed, and all E002 evaluations were labeled retrospective.

| Priority | Question | Candidate experiment | Gate |
| --- | --- | --- | --- |
| 1 | Are score probabilities and draw frequencies systematically wrong? | Compare independent Poisson with Dixon–Coles; inspect low-score residuals and calibration by season. | Full valid score PMF, unbounded sampling or an explicit certified tail bound, observed-score NLL and H/D/A scores. No automatic acceptance of a lower in-sample fit error. |
| 2 | Does Elo calibration transfer from its replay warm-up to final ratings? | Prespecify a chronological calibration or burn-in ablation of M3; then assess K and home advantage only in earlier folds. | E002 underpredicts aggregate draws. Separate this diagnostic from proof of a cause; version update order, seasonal resets and promotion priors, and keep tuning inside historical folds. |
| 3 | How much recency is useful? | Compare a small prespecified set of time-decay settings; then a simple dynamic attack/defense process if the gain warrants it. | Rolling outer evaluation with all tuning confined to earlier dates. Include compute cost and uncertainty, not just the best point estimate. |
| 4 | Can Championship continuity improve promoted-team starts? | Add a division-aware prior or an estimated cross-division strength offset, with explicit season transitions. | Existing canonical IDs support joining the leagues. Do not pool their raw goal rates as if the opponents were equally strong; evaluate promoted teams separately. |
| 5 | Do lagged shots improve prediction? | Add past-match shot/shot-on-target aggregates from the already cached data. | PL fields are complete in this audit; feature availability must use prior dates only, with source-definition changes documented. |
| 6 | Can the system forecast the current remainder? | Audit a full live fixture source and archive its observation times. | Validate freshness, statuses, 20 participants and all remaining ordered pairs. Probe authentication before writing the adapter. |
| 7 | Is richer information worth its maintenance burden? | Audit Understat xG and player/availability archives before modeling; assess market combination separately. | Confirm longitudinal coverage and point-in-time availability. Missing timestamps, unstable access or unsuitable permissions keep a source optional. |

Each experiment should specify its hypothesis, information cutoff, minimum effect
of interest, model/config version and split policy before evaluation. Report
proper scores, classwise calibration, per-season behavior, paired uncertainty,
and score likelihood when supported. New performance claims need a fresh outer
evaluation; rerunning E001 is verification, not new evidence of generalization.

The first data inventory found ample freely downloadable score history, useful
shot fields, and no authentication need for the existing pipeline. StatsBomb's
open PL panel is discontinuous; FBref's former advanced data are no longer a
reliable dependency. The unauthenticated football-data.org match endpoint returned
403, so evaluating that service would require a user-configured API token. A token
is not currently required and is not assumed to solve coverage or freshness.

European qualification remains conditional on supplied cup and slot assumptions.
An unconditional forecast would need models for those competitions, UEFA
performance slots and applicable eligibility rules. Do not rename top-five
probability as a Champions League qualification forecast.
