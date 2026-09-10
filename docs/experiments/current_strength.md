# API-Football team signals as current-strength information

## Decision

Record this as a post-MVP research lead, not a build. The archive's API-Football
per-match team statistics are valid and, in the Championship, genuinely new: they
carry the only expected goals this archive holds for the second league. But on the
cheap test the memo asked for, none of them establishes incremental information
about a team's later goals beyond what the M7 state already implies. Effects are of
order 1e-4 in log1p-goals MSE, most season-clustered intervals cross zero, and the
Premier League comparison is adverse. That is not a large, stable, actionable
signal, so no feature, lag, transformation, model variant or architecture work
follows from it.

The negative result is about this test, not about the hypothesis. A regression of
realized later goals on a residualized sensor asks whether the sensor beats the
state at predicting a noisy count. It does not ask whether admitting the sensor as a
likelihood would sharpen the latent posterior, which is a different question with a
different answer surface. Nothing here licenses the claim that process observations
cannot improve current-state filtering in the Championship.

## What the archive turned out to hold

Fixture detail captures already carried per-team match statistics that were never
normalized. They now publish to a canonical `team_statistics` table: shots by
location, blocked shots, possession, corners, passing, goalkeeper saves, cards, and
from 2022/23 the provider's own expected goals and goals prevented.

Regular-season coverage is complete in both leagues from 2017/18 (2016/17
Championship reaches 69%). Expected goals covers the Premier League from 2022/23 at
51%, then in full; it covers the Championship in full from 2023/24 and 97% of the
current season so far. Nearly all of it is retrospective evidence: 18,444 of 18,486
retained team-matches were captured by backfill, and only the current season's rows
were captured live.

## Validity against retained providers

The overlapping fields have known answers, which is what makes them a check.

| League | API-Football field | Retained comparator | Team-matches | Identical | Correlation | Mean difference |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| PL | `shots_total` | football-data shots | 7,659 | 97.0% | 0.9982 | +0.016 |
| PL | `shots_on_goal` | football-data SOT | 7,659 | 98.9% | 0.9982 | +0.003 |
| PL | `expected_goals` | Understat xG | 2,726 | 0% | 0.9369 | −0.116 |
| Championship | `shots_total` | football-data shots | 10,807 | 94.6% | 0.9959 | +0.015 |
| Championship | `shots_on_goal` | football-data SOT | 10,807 | 97.7% | 0.9972 | −0.001 |

Shot counts are the same measurement: the two providers agree exactly on 95–99% of
team-matches and correlate above 0.995. The expected-goals comparison behaves
differently and should: no pair is identical, correlation is 0.937, and API-Football
runs 0.116 goals lower per team-match than Understat. These are two xG models, not
one quantity measured twice, and neither is truth. Championship expected goals has
no retained comparator at all, which is exactly why it is interesting and exactly
why it cannot be validated the same way.

## Incremental information over the M7 state

At each source match the frozen M7 fixed-p=0.2 member supplies the team's log-rate
mean and variance from strictly earlier evidence. The candidate signal is that
match's own statistic. The target is the team's goals one, three or six team-matches
later in the same season. Controls are the state's own forecast for the target
fixture, both rate variances, home indicators and the calendar gap. Residualization
and pooled regression fit only earlier seasons with matured targets, and every
sensor subset shares complete cases within a league and horizon. Intervals are
paired 95% bootstrap intervals resampling whole seasons.

Next-match MSE differences against the state-only diagnostic; negative means
improvement.

| Study | League | Candidate | MSE difference | 95% interval | Seasons improved |
| --- | --- | --- | ---: | --- | ---: |
| Box shots | Championship | inside-box shots | −0.000131 | [−0.000415, +0.000213] | 7/9 |
| Box shots | Championship | goals + inside-box shots | −0.000100 | [−0.000363, +0.000250] | 7/9 |
| Box shots | PL | inside-box shots | −0.000075 | [−0.000387, +0.000206] | 3/9 |
| Box shots | PL | goals + inside-box shots | +0.000044 | [−0.000370, +0.000464] | 4/9 |
| Expected goals | Championship | API xG | −0.000259 | [−0.000666, +0.000147] | 1/2 |
| Expected goals | Championship | goals + API xG | −0.000088 | [−0.000580, +0.000403] | 1/2 |
| Expected goals | PL | API xG | +0.000692 | [+0.000096, +0.001571] | 0/3 |
| Expected goals | PL | Understat xG | +0.000037 | [−0.000358, +0.000423] | 1/3 |
| Expected goals | PL | goals + Understat xG + API xG | +0.001973 | [+0.000099, +0.004665] | 0/3 |

The Championship directions are the encouraging ones and the intervals do not
support them. Inside-box shots improve seven of nine seasons at a pooled effect of
−0.00013, which is about a thousandth of the state-only residual scale, with an
interval twice as wide as the effect. Championship expected goals points the same
way over the only two seasons that can be tested chronologically.

One interval does exclude zero favourably: adding API expected goals to goals in the
Championship scores −0.000418 [−0.000463, −0.000373]. It should not be read as
evidence. That interval resamples two season clusters, which is not an interval so
much as a restatement of two numbers, and the same candidate against the state-only
comparator crosses zero comfortably.

The Premier League results run the other way and are the more informative half. API
expected goals is worse than the state alone by +0.00069 with an interval clear of
zero, it is worse than Understat xG, and adding it to Understat xG makes that worse
still. Given the two xG series correlate 0.937 with a 0.116 level offset, the
straightforward reading is measurement difference rather than extra information.

## Limits

Expected goals has three chronologically testable Premier League seasons and two in
the Championship, because the first covered season has to be training. Season
clusters that few make the interval machinery weak in both directions, and no result
here should be strengthened by pooling leagues or horizons after the fact.

The targets are realized goals, which is a noisy and indirect outcome. The controls
are the state's own forecast rather than the state itself, so the test measures
information beyond what the state predicts, not information beyond what the state
contains. Retrospective capture means these statistics were not available at the
historical cutoffs they are evaluated at; the availability assumption is the same
next-day convention the retained goals/xG study uses, and it is an assumption.

## Reproducing

`runs/current-strength-v1`, from the research manifest frozen as
`runs/research-ready-v2-statistics/manifest.json`. 51,520 extracted observations;
50,708 complete cases over ten seasons for box shots and 16,402 over four seasons for
expected goals. The [audit](current_strength/audit.json),
[coverage](current_strength/coverage.csv),
[provider agreement](current_strength/provider_agreement.csv),
[headlines](current_strength/headlines.json) and both study reports are retained
here. The 56 MB observation extract stays under Git-ignored `runs/`; its SHA-256 is
`162c3530d96126af14254a0177db3ca276c5aaa0851dd0c89d54affc9c1fb080`.

```sh
uv run python scripts/audit_team_statistics.py --output runs/team-statistics-audit
uv run python scripts/freeze_research.py --output runs/research-ready/manifest.json
OPENBLAS_NUM_THREADS=1 uv run --locked --all-extras python scripts/evaluate_current_strength.py \
  --manifest runs/research-ready/manifest.json --output runs/current-strength
```
