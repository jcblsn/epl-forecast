"""Postseason tournament simulation kept separate from regular-season fitting."""

from datetime import date, timedelta

import numpy as np

from epl_forecast.data.rules import league_rules
from epl_forecast.schema import Fixture, fixture_id


class _MarginalLegs:
    """Postseason scores from the forecast's marginal match distribution."""

    conditioning = "common forecast distribution resampled per path"

    def __init__(self, model):
        self.model = model

    def sample(self, fixture, selected, rng):
        scores = self.model.predict_match(fixture).scores
        if scores is None:
            raise ValueError("Championship playoffs require a score-generating model")
        return scores.sample(rng, len(selected))


class _PathLegs:
    """Postseason scores from the same latent state that produced the path's table.

    A club enters the bracket at the strength its own path gave it, so qualifying is
    evidence about that path rather than a reset to the league-wide marginal. The
    effect is a selection one and runs in either direction: a club whose marginal
    state is weak only reaches the playoffs on paths where it was drawn strong, while
    one strong enough to go up automatically on a good path arrives having been drawn
    worse than average.
    """

    conditioning = "path-specific latent team states carried from the regular season"

    def __init__(self, states):
        self.states = states

    def sample(self, fixture, selected, rng):
        return self.states.sample_scores(fixture, rng, selected)


def _sample_legs(legs, home, away, day, competition, season, rng):
    home = np.asarray(home)
    away = np.asarray(away)
    home_goals = np.empty(len(home), dtype=int)
    away_goals = np.empty(len(home), dtype=int)
    for h, a in sorted(set(zip(home, away, strict=True))):
        selected = np.flatnonzero((home == h) & (away == a))
        fixture = Fixture(
            fixture_id(competition, season, str(h), str(a)),
            competition,
            season,
            day,
            str(h),
            str(a),
        )
        home_goals[selected], away_goals[selected] = legs.sample(fixture, selected, rng)
    return home_goals, away_goals


def _single_match_winner(legs, first, second, day, competition, season, rng, neutral=False):
    first = np.asarray(first)
    second = np.asarray(second)
    if neutral:
        first_home = rng.random(len(first)) < 0.5
        home = np.where(first_home, first, second)
        away = np.where(first_home, second, first)
    else:
        first_home = np.ones(len(first), dtype=bool)
        home, away = first, second
    home_goals, away_goals = _sample_legs(legs, home, away, day, competition, season, rng)
    home_wins = home_goals > away_goals
    tied = home_goals == away_goals
    home_wins[tied] = rng.random(tied.sum()) < 0.5
    first_wins = np.where(first_home, home_wins, ~home_wins)
    return np.where(first_wins, first, second)


def _two_leg_round(legs, ties, days, competition, season, rng):
    """Both semi-finals, in calendar order so a forward state advances once per date."""
    first = [
        _sample_legs(legs, lower, higher, day, competition, season, rng)
        for (higher, lower), day in zip(ties, days[:2], strict=True)
    ]
    second = [
        _sample_legs(legs, higher, lower, day, competition, season, rng)
        for (higher, lower), day in zip(ties, days[2:], strict=True)
    ]
    winners = []
    for (higher, lower), away_first, home_second in zip(ties, first, second, strict=True):
        higher_goals = away_first[1] + home_second[0]
        lower_goals = away_first[0] + home_second[1]
        higher_wins = higher_goals > lower_goals
        tied = higher_goals == lower_goals
        higher_wins[tied] = rng.random(tied.sum()) < 0.5
        winners.append(np.where(higher_wins, higher, lower))
    return winners


def _playoff_days(season, last_regular_day):
    day = date.fromisoformat(str(last_regular_day))
    season_end = date(int(season[5:]), 7, 31)
    available = max((season_end - day).days, 0)
    scale = min(1.0, available / 29)
    offsets = [round(offset * scale) for offset in (7, 8, 14, 15, 21, 22, 29)]
    return day, [day + timedelta(days=offset) for offset in offsets], scale


PLAYOFF_FORMATS = {4: "four-team-five-match", 6: "2026-six-team-seven-match"}


def playoff_format(rules) -> str:
    try:
        return PLAYOFF_FORMATS[rules.playoff_places]
    except KeyError:
        raise ValueError(f"No bracket for {rules.playoff_places} playoff places") from None


def simulate_playoffs(
    model, orders, teams, competition, season, last_regular_day, rng, states=None
):
    """Return one playoff winner per regular-season path.

    The bracket starts at the first place below automatic promotion, so the same
    code serves every EFL division. Six places add the reviewed 2026/27 Championship
    quarter-finals, after which the semi-finals are reseeded; four places go straight
    to semi-finals of first against fourth and second against third. Semi-finals are
    two-legged. A 50/50 virtual home designation removes expected home advantage in
    the neutral final. Tied knockout scores use an explicit equal extra-time/penalty
    approximation because retained rules do not specify a model.

    Team IDs are represented by their indices while sampling. The structural model
    sees the real IDs. When the season simulation drew joint latent states, the
    bracket is played out on those same draws, so a path's postseason inherits the
    strengths its table came from. Rounds are then sampled in calendar order, because
    a forward-evolving state cannot be asked for an earlier date once it has advanced.
    """
    rules = league_rules(competition, season)
    format_name = playoff_format(rules)
    order = np.asarray(orders, dtype=int)
    if order.ndim != 2 or order.shape[1] != len(teams):
        raise ValueError("Playoff simulation requires one complete order per path")
    legs = _MarginalLegs(model) if states is None else _PathLegs(states)
    if states is not None and states.size != len(order):
        raise ValueError("Sampled states and regular-season paths must correspond")
    ids = np.asarray(teams)
    _, playoff_days, date_scale = _playoff_days(season, last_regular_day)
    first = rules.automatic_promotion

    def team_ids(place):
        return ids[np.asarray(order[:, first + place], dtype=int)]

    if rules.playoff_places == 6:
        qf1 = _single_match_winner(
            legs, team_ids(2), team_ids(5), playoff_days[0], competition, season, rng
        )
        qf2 = _single_match_winner(
            legs, team_ids(3), team_ids(4), playoff_days[1], competition, season, rng
        )
        rank_by_path = [{ids[index]: rank for rank, index in enumerate(path)} for path in order]
        lower = np.array(
            [
                max(a, b, key=lambda team: ranks[team])
                for a, b, ranks in zip(qf1, qf2, rank_by_path, strict=True)
            ]
        )
        higher = np.where(lower == qf1, qf2, qf1)
        semi1_high, semi1_low = team_ids(0), lower
        semi2_high, semi2_low = team_ids(1), higher
    else:
        semi1_high, semi1_low = team_ids(0), team_ids(3)
        semi2_high, semi2_low = team_ids(1), team_ids(2)
    finalist1, finalist2 = _two_leg_round(
        legs,
        [(semi1_high, semi1_low), (semi2_high, semi2_low)],
        [playoff_days[2], playoff_days[3], playoff_days[4], playoff_days[5]],
        competition,
        season,
        rng,
    )
    winners = _single_match_winner(
        legs,
        finalist1,
        finalist2,
        playoff_days[6],
        competition,
        season,
        rng,
        neutral=True,
    )
    return winners, {
        "format": format_name,
        "regular_season_conditioning": "one simulated bracket per final-table path",
        "state_conditioning": legs.conditioning,
        "match_model": "structural score distribution at synthetic postseason dates",
        "semi_final_home_order": "higher regular-season seed at home in the second leg",
        "final_site": "neutral via an equal mixture of virtual home designations",
        "tied_knockout_scores": "equal advancement chance after modeled regulation scores",
        "synthetic_match_dates": [str(value) for value in playoff_days],
        "date_offset_scale": date_scale,
        "date_treatment": (
            "default 7/8/14/15/21/22/29-day offsets after the regular season"
            if date_scale == 1
            else "offsets compressed proportionally to remain inside the season schema"
        ),
    }
