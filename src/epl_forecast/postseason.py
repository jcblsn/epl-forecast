"""Postseason tournament simulation kept separate from regular-season fitting."""

from datetime import date, timedelta

import numpy as np

from epl_forecast.schema import Fixture, fixture_id


def _sample_legs(model, home, away, day, season, rng):
    home = np.asarray(home)
    away = np.asarray(away)
    home_goals = np.empty(len(home), dtype=int)
    away_goals = np.empty(len(home), dtype=int)
    for h, a in sorted(set(zip(home, away, strict=True))):
        selected = np.flatnonzero((home == h) & (away == a))
        fixture = Fixture(
            fixture_id("eng-championship", season, str(h), str(a)),
            "eng-championship",
            season,
            day,
            str(h),
            str(a),
        )
        scores = model.predict_match(fixture).scores
        if scores is None:
            raise ValueError("Championship playoffs require a score-generating model")
        sampled = scores.sample(rng, len(selected))
        home_goals[selected], away_goals[selected] = sampled
    return home_goals, away_goals


def _single_match_winner(model, first, second, day, season, rng, neutral=False):
    first = np.asarray(first)
    second = np.asarray(second)
    if neutral:
        first_home = rng.random(len(first)) < 0.5
        home = np.where(first_home, first, second)
        away = np.where(first_home, second, first)
    else:
        first_home = np.ones(len(first), dtype=bool)
        home, away = first, second
    home_goals, away_goals = _sample_legs(model, home, away, day, season, rng)
    home_wins = home_goals > away_goals
    tied = home_goals == away_goals
    home_wins[tied] = rng.random(tied.sum()) < 0.5
    first_wins = np.where(first_home, home_wins, ~home_wins)
    return np.where(first_wins, first, second)


def _two_leg_winner(model, higher, lower, first_day, second_day, season, rng):
    first_home, first_away = _sample_legs(model, lower, higher, first_day, season, rng)
    second_home, second_away = _sample_legs(model, higher, lower, second_day, season, rng)
    higher_goals = first_away + second_home
    lower_goals = first_home + second_away
    higher_wins = higher_goals > lower_goals
    tied = higher_goals == lower_goals
    higher_wins[tied] = rng.random(tied.sum()) < 0.5
    return np.where(higher_wins, higher, lower)


def simulate_championship_playoffs(model, orders, teams, season, last_regular_day, rng):
    """Return one playoff winner per regular-season path.

    Team IDs are represented by their indices while sampling. The structural model
    sees the real IDs. Quarter-finals use the reviewed 2026/27 bracket; semi-finals
    are two-legged and reseeded. A 50/50 virtual home designation removes expected
    home advantage in the neutral final. Tied knockout scores use an explicit equal
    extra-time/penalty approximation because retained rules do not specify a model.
    """
    order = np.asarray(orders, dtype=int)
    if order.ndim != 2 or order.shape[1] != len(teams):
        raise ValueError("Playoff simulation requires one complete order per path")
    ids = np.asarray(teams)
    day = date.fromisoformat(str(last_regular_day))

    def team_ids(indices):
        return ids[np.asarray(indices, dtype=int)]

    if int(season[:4]) >= 2026:
        qf1 = _single_match_winner(
            model,
            team_ids(order[:, 4]),
            team_ids(order[:, 7]),
            day + timedelta(days=7),
            season,
            rng,
        )
        qf2 = _single_match_winner(
            model,
            team_ids(order[:, 5]),
            team_ids(order[:, 6]),
            day + timedelta(days=8),
            season,
            rng,
        )
        rank_by_path = [{ids[index]: rank for rank, index in enumerate(path)} for path in order]
        lower = np.array(
            [
                max(a, b, key=lambda team: ranks[team])
                for a, b, ranks in zip(qf1, qf2, rank_by_path, strict=True)
            ]
        )
        higher = np.where(lower == qf1, qf2, qf1)
        semi1_high, semi1_low = team_ids(order[:, 2]), lower
        semi2_high, semi2_low = team_ids(order[:, 3]), higher
        format_name = "2026-six-team-seven-match"
    else:
        semi1_high, semi1_low = team_ids(order[:, 2]), team_ids(order[:, 5])
        semi2_high, semi2_low = team_ids(order[:, 3]), team_ids(order[:, 4])
        format_name = "legacy-four-team-five-match"
    finalist1 = _two_leg_winner(
        model,
        semi1_high,
        semi1_low,
        day + timedelta(days=14),
        day + timedelta(days=21),
        season,
        rng,
    )
    finalist2 = _two_leg_winner(
        model,
        semi2_high,
        semi2_low,
        day + timedelta(days=15),
        day + timedelta(days=22),
        season,
        rng,
    )
    winners = _single_match_winner(
        model,
        finalist1,
        finalist2,
        day + timedelta(days=29),
        season,
        rng,
        neutral=True,
    )
    return winners, {
        "format": format_name,
        "regular_season_conditioning": "one simulated bracket per final-table path",
        "match_model": "structural score distribution at synthetic postseason dates",
        "semi_final_home_order": "higher regular-season seed at home in the second leg",
        "final_site": "neutral via an equal mixture of virtual home designations",
        "tied_knockout_scores": "equal advancement chance after modeled regulation scores",
    }
