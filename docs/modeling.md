# Forecasting and simulation conventions

## Models and experiment settings

All models fit independently before each prediction date using only results
from earlier dates within the configured 1,095-day window. No team identities from
later fixtures are used to build a model's training vocabulary.

| Version | Description | Data used |
| --- | --- | --- |
| M0-frequency-v1 | Historical H/D/A counts with one prior count per outcome. | Past PL outcomes. |
| M1-league-poisson-v1 | Independent goals with league home/away rates; one virtual 1–1 match prevents degenerate rates. | Past PL scores, exponentially weighted with 365-day half-life. |
| M2-attack-defense-v1 | Ridge-regularized team attack and defense, league scoring level and home advantage. | Same score history and time weights as M1. |
| M3-elo-ordered-logit-v1 | Elo updates followed by a regularized ordered-logit outcome layer. | Past PL outcomes, with chronological pre-update calibration features. |

For M2, with attack `a`, defensive strength `d`, intercept `b` and home advantage `h`:

```text
log(home rate) = b + h + a[home] - d[away]
log(away rate) = b     + a[away] - d[home]
```

Attack and defense vectors each sum to zero. Fit minimizes weighted Poisson
negative log likelihood plus `ridge / 2 * sum(a² + d²)`, with ridge 5, and the same
virtual league match as M1. SciPy L-BFGS-B uses an analytic gradient; numerical
derivative tests check it. Failed optimization is an error. Unseen teams get zero
attack/defense deviations, an explicit league-average prior. This is a weakness
for promoted clubs and is not an estimated promotion penalty.

M2 is an independent Poisson baseline, not an implementation of the Dixon–Coles
low-score correction. The [original Dixon–Coles paper](https://doi.org/10.1111/1467-9876.00065)
motivates comparison with time-weighted team-level score models. Its results do
not establish that a correction or a decay setting will improve this dataset.

H/D/A probabilities use the full Skellam goal-difference distribution. Observed
score likelihoods use full Poisson log PMFs. Display grids report omitted tail
mass and are not renormalized. Simulation samples unbounded goal counts directly.

M3 starts ratings at zero for each training-window replay, adds a fixed 60-point
home advantage to the Elo expectation and uses K = 20. Same-day matches receive
batch updates after all their pre-match features have been recorded. The draw
layer fits an intercept, nonnegative slope and positive threshold to historical
pre-update rating differences, with a ridge penalty of 1. Unseen clubs have the
zero initial rating. It has no seasonal resets, division offset or goal-margin
update and supplies no score distribution. The [E002 protocol and report](experiments/E002.md)
give its exact formulas, initialization, decision rule and retrospective results.
M2 remains the provisional reference after this comparison.

## Evaluation

Dates, rather than kickoff order, define rolling origins. `available_on` is an
explicit next-day convention; it cannot eliminate retrospective source revisions.
Models refit using prior results throughout each evaluation split, as a deployed
daily forecasting system would. Hyperparameters remain fixed.

Log loss uses natural logarithms and clips exact zero class probabilities at
`1e-15` for reporting. Brier sums squared errors over all three classes, with range
0–2. Score NLL is the negative mean observed-score log probability. Classwise ECE
uses ten equal-width probability bins per class, then averages the three weighted
absolute calibration errors. Empty bins have null means. ECE is a descriptive
diagnostic, not a proper scoring rule; a low-resolution league-frequency forecast
can have excellent aggregate calibration and weak predictive accuracy.

When requested, paired loss differences resample 28-day blocks, kept within season boundaries and
pooled across seasons, using 2,000 bootstrap replicates. The intervals reflect
sampling sensitivity, not all model/parameter uncertainty or a guarantee of future
performance. One season provides few independent blocks. Every comparison uses
the intersection of match IDs; market-matched tables disclose sample sizes.

Market probabilities normalize inverse decimal odds by their sum. This is simple
proportional margin removal, not a calibrated market model. Individual collection
times are missing and closing quotes have a later information horizon than our
start-of-day forecasts. No market prices enter structural-model fitting.

The original three chronological splits are development 2015/16–2022/23, validation
2023/24–2024/25 and holdout 2025/26. The baseline selection file was written after
validation and before the holdout evaluation. All these historical periods now
contribute development evidence. Use rolling seasonal CV for new ideas, selecting
hyperparameters from earlier seasons when evaluating a tuned strategy. The small
M2 search in `scripts/tune_m2.py` uses this rule. Bootstrap analysis is optional
(`bootstrap_samples = 0` or omitted skips it); exploratory work has no minimum-gain
or confidence-interval gate. Archived live forecasts are the forward test.

## Season simulation

The CLI reconstructs a historical season's participants and recorded fixture
dates. It validates all 380 ordered opponent pairs, fixes all scores available at
the cutoff, removes future score labels, fits once at the cutoff, and samples each
remaining fixture once per draw. It does not update team strength from simulated
scores. Draws reflect match randomness conditional on fitted parameters; they omit
parameter uncertainty, transfers, injuries and future managerial changes.

Points are 3/1/0. Rank by points, goal difference and goals scored. Apply
head-to-head points and away goals only for ties affecting the title, relegation
or the supplied European allocation. The
[head-to-head rule began in 2019/20](https://www.premierleague.com/en/news/1262217);
the [2025/26 handbook, section C](https://resources.premierleague.pulselive.com/premierleague/document/2025/07/24/99839920-d274-42aa-a2ac-e5612b4f6c61/PL_Handbook_25-26_Digital_24.07.pdf)
defines the implemented sequence. Nondecisive ties remain shared and their probability
mass is split across occupied ranks for reporting. If a decisive tie remains,
assume equal playoff chances and report its incidence. This is an explicit
approximation, including multi-team ties whose playoff arrangements are unspecified.

The bundled 2023/24 sanction history applies Everton's initial −10, subsequent +4
appeal adjustment, then −2, and Forest's −4 only after their announcement dates.
Events become usable the next day to preserve the start-of-day convention.
Sources are stored with [each event](../src/epl_forecast/data/pl_adjustments.json).
`--adjustments path.json` supplies a complete override list with `team_id`, integer
`points`, `known_on`, and `source`; future-known entries are rejected. No future
sanctions or appeals are forecast. The small bundled registry is not an automatic
comprehensive disciplinary feed.

Top-four and top-five are position events. European qualification output requires
an explicit scenario: four or five league UCL places plus named FA Cup and EFL Cup
winners. It accounts for domestic cup pass-downs and cup winners outside the PL.
It is conditional on those assumptions and on no additional English UEFA
titleholders or eligibility exclusions. The
[Premier League's qualification explanation](https://www.premierleague.com/en/european-qualification-explained)
shows why league ranks alone cannot determine every European place.

The `forecast` command uses a captured FPL full-season schedule. It checks season,
identities, all 380 pairs and completion statuses, cross-checks available current
Football-Data results, and retains the observation time. Fitting excludes the
snapshot's London date; the live table fixes all scores already full-time in the
snapshot, including that date. The optional `results_observed_at` simulation input
supports this separation; historical simulation retains its next-day cutoff.

Undated/postponed fixtures keep their raw kickoff information in exports and use
a placeholder date only inside the fixed-strength model. In-progress or overdue
fixtures suspend the season projection while other predictions remain available.
These forecasts do not constitute an in-play model. See [live operations](live.md)
for freshness, archival behavior and the initial 2026/27 forecast.
