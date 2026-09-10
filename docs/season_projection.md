# The 2026/27 season projection: what it says and how far to trust it

This is the batch's answer document. It states what the pinned projection claims,
where its uncertainty comes from, whether the model behind it is historically
defensible in each league, and what the Championship promotion numbers actually
mean. Every figure below is already in a committed artifact; nothing here needs
to be recomputed.

## What M7 believes about each club's final rank

The [pinned 2026/27 projection](experiments/current_season_projection_2026-09-10/report.md)
is the answer, taken at one recorded information cutoff,
`2026-09-10T14:42:02+00:00`, with 50,000 simulations and seed 20260910. It holds
the full finishing-position probability vector for all 44 clubs, not just expected
rank: [rank_probabilities.csv](experiments/current_season_projection_2026-09-10/rank_probabilities.csv)
is one row per club and position, and
[table.csv](experiments/current_season_projection_2026-09-10/table.csv) carries
expected and median rank and points, 50/80/90% intervals for both, and every
headline event probability. Both join on competition, season, forecast timestamp
and club, so an external comparison can be attached later without re-deriving
anything.

Arsenal lead the Premier League on 53.4% for the title and Manchester City follow
on 30.4%; Coventry and Ipswich carry the largest relegation probabilities at 61%.
Southampton lead the Championship on 54.8% promotion. The distributions are wide:
the mean 90% rank interval spans 12.5 positions in the Premier League and 17.0 in
the Championship, three matchweeks into the season.

## Where that uncertainty comes from

Three matched variants change one assumption each and hold the score law, fixtures
and information set fixed. Distances are against full M7; the Monte Carlo
replication row in the same artifact establishes what counts as noise.

| Competition | Variant | Mean 90% rank width change | Mean rank W1 | Largest event move |
| --- | --- | ---: | ---: | --- |
| Premier League | Current-state uncertainty removed | −1.00 (−8%) | 0.352 | Ipswich relegation +6.3pp |
| Premier League | Future innovations removed | −0.45 (−4%) | 0.146 | Arsenal title +2.9pp |
| Premier League | Promoted clubs' entry uncertainty removed | −0.30 (−2%) | 0.082 | Ipswich relegation +1.9pp |
| Championship | Current-state uncertainty removed | −1.92 (−11%) | 0.746 | Southampton automatic promotion +11.2pp |
| Championship | Future innovations removed | −0.25 (−1%) | 0.133 | Bolton relegation +1.6pp |

Current-state uncertainty matters more than assumed future evolution, and much
more so in the Championship: replacing the state posterior with its mean moves
Championship rank distributions more than five times as far as removing future
innovations, against roughly twice as far in the Premier League. Every event
probability moves away from the middle: narrowing a club's distribution pushes
mass toward its modal outcome, so Ipswich's relegation probability rises rather
than falls when uncertainty is taken out. That asymmetry is what a
league with no xG channel and noisier club states should show.

Neither assumption is where most of the width lives. The largest single variant
removes 1.9 rank positions of a 17.0-position interval. The rest is match-outcome
randomness given a state path, which no state assumption can remove. Both
variants clear Monte Carlo noise for essentially every club — 20/20 and 24/24 for
the posterior-mean contrast — so the ordering above is a real property of the
model, not simulation error.

The promoted-club contrast is the early-season diagnostic: fixing the three
promoted Premier League clubs' entry states at their posterior means removes only
2% of mean rank width, and its largest effect is on Ipswich's relegation
probability. Promoted-entry uncertainty is a small part of the September picture,
because by then those clubs have played.

## Whether the model is historically defensible

Yes, in both leagues, on separate evidence.

The [Premier League panel](experiments/season_scoring.md) covers 220 club-seasons
over 2015/16–2025/26 and favors M7 on rank RPS at preseason through MW19 and on
points CRPS after preseason, with much better interval coverage than M2.

The [Championship panel](experiments/season_scoring_championship.md) is new and
covers 264 club-seasons over the same eleven seasons. M7 beats M2 on rank RPS at
preseason, MW6, MW12 and MW19, on points CRPS through MW12, and on every preseason
event Brier, each with a season-clustered interval excluding zero. Its PIT
histograms are close to uniform at every origin where M2's are U-shaped.

Building that panel found a real defect. A Championship forecast made before a
club's first match of the season reset every returning club to the flat league
population prior — 19 of 24 clubs at the 2025/26 preseason cutoff — because the
promotion bridge's source is the previous Championship season. Correcting it moved
preseason Championship rank RPS from 0.1665 to 0.1513 and mean points SD from 19.8
to 12.6. The Premier League path is unchanged, and regenerating the pinned 2026/27
artifact from the same cutoff and seed reproduces its report, tables and heatmaps
byte for byte, because every Championship club had already played by 10 September.

The [relegation entry-state comparison](experiments/relegation_entry.md) tested the
remaining suspicion, that the Championship model wastes what it knows about clubs
arriving from the Premier League. Over 30 relegated club-seasons, neither a generic
relegated-club prior nor an opponent-adjusted mapping from the club's Premier
League season improves its first ten Championship matches or its season
distribution, and both narrow the points interval enough to cost coverage. Almost
all of the estimated signal is the division-level shift of about +0.23 log rate;
the within-Premier-League slope is 1.0 to 1.5 standard errors from zero. The
current treatment stays.

Relegated clubs remain the worst-scored Championship cohort for both models, and
both under-predict them. That is a known, measured, unresolved weakness, not an
unexamined one.

## What the Championship promotion probabilities mean

They come from simulating the actual 2026/27 six-team bracket after every
regular-season path, with the same structural score model: single-match
quarter-finals for the clubs finishing fifth to eighth, two-legged reseeded
semi-finals in which third and fourth enter, and a neutral final. Postseason logic
is in `postseason.py` and never enters regular-season fitting.

The structure is visible in the numbers. Conditional on qualifying, promotion
probability ranges from 5.8% for Bolton to 29.0% for Southampton, and from 13.0%
to 29.0% among the twelve likeliest qualifiers, against the 16.7% an equal-chances
placeholder would assign every one of them. Third and fourth place skip a knockout
round, and stronger clubs win more ties, so both seeding and strength move the
number. Six qualifiers and one promotion are conserved exactly across paths.

Three approximations remain explicit rather than hidden: tied knockout scores
resolve on an equal advancement chance because the retained rules do not specify
extra time or penalties, the neutral final uses a 50/50 virtual home designation,
and postseason dates are synthetic offsets from the last regular-season match,
compressed if the season schema leaves less room. All three are recorded in each
forecast's `playoff_model` block.

## What this batch did not do

No new model family was opened. Market pooling was left as it stands, with the
retained fit still placing full weight on the market; M7 is the primary forecast
surface in both leagues. M4 and M5 were not added to the Championship panel,
because a four-model run extrapolated to roughly seven hours of refitting. The player bridge,
cross-division architecture, score-law search and scouting model stayed closed.
No public forecast, bookmaker price or prediction market was scraped or fitted;
the artifact is shaped so that comparison can happen later against its recorded
timestamp.
