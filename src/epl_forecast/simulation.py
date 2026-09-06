from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from zoneinfo import ZoneInfo

import numpy as np

from epl_forecast.models.base import ForecastModel
from epl_forecast.schema import Fixture, Match


@dataclass(frozen=True)
class EuropeScenario:
    name: str
    champions_league_places: int
    fa_cup_winner: str
    efl_cup_winner: str

    def __post_init__(self) -> None:
        if self.champions_league_places not in (4, 5):
            raise ValueError("Supported European scenarios have four or five league UCL places")
        if not self.name or not self.fa_cup_winner or not self.efl_cup_winner:
            raise ValueError("A European scenario needs a name and both domestic cup winners")


def european_places(order: list[str], scenario: EuropeScenario) -> dict[str, set[str]]:
    champions = set(order[: scenario.champions_league_places])
    europa = set() if scenario.fa_cup_winner in champions else {scenario.fa_cup_winner}
    for team in order:
        if len(europa) == 2:
            break
        if team not in champions:
            europa.add(team)
    if scenario.efl_cup_winner not in champions | europa:
        conference = {scenario.efl_cup_winner}
    else:
        conference = {next(team for team in order if team not in champions | europa)}
    return {"champions_league": champions, "europa_league": europa, "conference_league": conference}


def decisive_group(
    order: list[int],
    start: int,
    end: int,
    teams: list[str],
    relegated: int,
    europe: EuropeScenario | None,
) -> bool:
    if end - start < 2:
        return False
    if start == 0 or start < len(teams) - relegated < end:
        return True
    if europe is None:
        return False
    baseline = european_places([teams[i] for i in order], europe)
    for a, b in combinations(range(start, end), 2):
        alternate = list(order)
        alternate[a], alternate[b] = alternate[b], alternate[a]
        if european_places([teams[i] for i in alternate], europe) != baseline:
            return True
    return False


def rank_table(
    teams: list[str],
    points: np.ndarray,
    goal_difference: np.ndarray,
    goals_for: np.ndarray,
    head_points: np.ndarray,
    head_away_goals: np.ndarray,
    rng: np.random.Generator,
    relegated: int = 3,
    head_to_head: bool = True,
    europe: EuropeScenario | None = None,
) -> tuple[list[int], list[tuple[int, int]], bool, bool]:
    order = list(map(int, np.lexsort((-goals_for, -goal_difference, -points))))
    tied_spans = []
    unresolved, used_head_to_head = False, False
    start = 0
    while start < len(teams):
        end = start + 1
        first = order[start]
        key = points[first], goal_difference[first], goals_for[first]
        while end < len(teams):
            team = order[end]
            if (points[team], goal_difference[team], goals_for[team]) != key:
                break
            end += 1
        group = order[start:end]
        critical = decisive_group(order, start, end, teams, relegated, europe)
        if len(group) > 1 and critical and head_to_head:
            used_head_to_head = True
            h2h_points = {i: int(head_points[i, group].sum()) for i in group}
            h2h_away = {i: int(head_away_goals[i, group].sum()) for i in group}
            group.sort(key=lambda i: (-h2h_points[i], -h2h_away[i]))
            order[start:end] = group
            keys = [(h2h_points[i], h2h_away[i]) for i in group]
        else:
            keys = [(0, 0)] * len(group)
        offset = 0
        while offset < len(group):
            stop = offset + 1
            while stop < len(group) and keys[stop] == keys[offset]:
                stop += 1
            if stop - offset > 1:
                left, right = start + offset, start + stop
                tied_spans.append((left, right))
                unresolved |= decisive_group(order, left, right, teams, relegated, europe)
                order[left:right] = list(map(int, rng.permutation(order[left:right])))
            offset = stop
        start = end
    return order, tied_spans, unresolved, used_head_to_head


def validate_schedule(
    teams: list[str],
    played: list[Match],
    remaining: list[Fixture],
    as_of: date,
    results_observed_at: datetime | None = None,
) -> None:
    if len(teams) != 20 or len(set(teams)) != 20:
        raise ValueError("Premier League simulation requires 20 distinct season participants")
    fixtures = [m.fixture for m in played] + remaining
    if len({f.season_id for f in fixtures}) != 1:
        raise ValueError("Simulation fixtures must belong to one season")
    if {f.competition_id for f in fixtures} != {"eng-premier-league"}:
        raise ValueError("Simulation supports Premier League fixtures only")
    pairs = [(f.home_team_id, f.away_team_id) for f in fixtures]
    expected = {(home, away) for home in teams for away in teams if home != away}
    if len(pairs) != 380 or len(set(pairs)) != 380 or set(pairs) != expected:
        raise ValueError(
            "Simulation requires every ordered opponent pair exactly once (380 matches)"
        )
    if results_observed_at is None:
        if any(match.available_on > as_of for match in played):
            raise ValueError("Played results must be available at the simulation cutoff")
    else:
        if (
            results_observed_at.tzinfo is None
            or results_observed_at.astimezone(ZoneInfo("Europe/London")).date() != as_of
        ):
            raise ValueError("Observed results must come from the model cutoff's calendar day")
        if any(match.fixture.match_date > as_of for match in played):
            raise ValueError("Played results postdate their snapshot observation")
    if any(fixture.match_date < as_of for fixture in remaining):
        raise ValueError("Remaining fixtures predate the simulation cutoff")


def simulate_season(
    model: ForecastModel,
    played: list[Match],
    remaining: list[Fixture],
    teams: list[str],
    as_of: date,
    simulations: int,
    seed: int,
    adjustments: list[dict] | None = None,
    europe: EuropeScenario | None = None,
    results_observed_at: datetime | None = None,
) -> dict:
    if type(simulations) is not int or simulations < 1:
        raise ValueError("simulations must be a positive integer")
    teams = sorted(teams)
    validate_schedule(teams, played, remaining, as_of, results_observed_at)
    if model.as_of != as_of:
        raise ValueError("Model fit cutoff must equal the season simulation cutoff")
    adjustments = adjustments or []
    team_index = {team: index for index, team in enumerate(teams)}
    point_offsets = np.zeros(len(teams), dtype=int)
    for adjustment in adjustments:
        if date.fromisoformat(adjustment["known_on"]) > as_of:
            raise ValueError("Point adjustment was not known at the simulation cutoff")
        if adjustment["team_id"] not in team_index or type(adjustment["points"]) is not int:
            raise ValueError("Invalid point adjustment")
        if not adjustment.get("source"):
            raise ValueError("Point adjustments require a provenance source")
        point_offsets[team_index[adjustment["team_id"]]] += adjustment["points"]
    rng = np.random.default_rng(seed)
    points = np.tile(point_offsets, (simulations, 1))
    goals_for = np.zeros_like(points)
    goals_against = np.zeros_like(points)
    head_points = np.zeros((simulations, len(teams), len(teams)), dtype=np.int16)
    head_away = np.zeros_like(head_points)
    draws = np.zeros(simulations, dtype=int)

    def add_result(fixture: Fixture, home_goals, away_goals) -> None:
        h, a = team_index[fixture.home_team_id], team_index[fixture.away_team_id]
        home_goals, away_goals = np.asarray(home_goals), np.asarray(away_goals)
        home_points = 3 * (home_goals > away_goals) + (home_goals == away_goals)
        away_points = 3 * (away_goals > home_goals) + (home_goals == away_goals)
        points[:, h] += home_points
        points[:, a] += away_points
        goals_for[:, h] += home_goals
        goals_for[:, a] += away_goals
        goals_against[:, h] += away_goals
        goals_against[:, a] += home_goals
        head_points[:, h, a] += home_points
        head_points[:, a, h] += away_points
        head_away[:, a, h] += away_goals
        draws[:] += home_goals == away_goals

    for match in sorted(played, key=lambda m: m.fixture.match_id):
        add_result(match.fixture, match.home_goals, match.away_goals)
    state_sampler = getattr(model, "sample_forecast_state", None)
    states = state_sampler(rng, size=simulations) if state_sampler and remaining else None
    if states is not None and (states.as_of != as_of or states.size != simulations):
        raise ValueError("Sampled forecast states must match the simulation cutoff and size")
    unknown_teams = set()
    known = getattr(model, "team_index", None)
    for fixture in sorted(remaining, key=lambda f: (f.match_date, f.match_id)):
        if known is not None:
            unknown_teams.update(
                t for t in (fixture.home_team_id, fixture.away_team_id) if t not in known
            )
        if states is not None:
            goals = states.sample_scores(fixture, rng)
        else:
            forecast = model.predict_match(fixture)
            if forecast.scores is None:
                raise ValueError("Season simulation requires a score-generating model")
            goals = forecast.scores.sample(rng, simulations)
        if any(
            np.shape(g) != (simulations,)
            or not np.issubdtype(np.asarray(g).dtype, np.integer)
            or np.any(np.asarray(g) < 0)
            for g in goals
        ):
            raise ValueError("Score samples must be nonnegative integer arrays, one per path")
        add_result(fixture, *goals)
    if not np.array_equal(goals_for.sum(axis=1), goals_against.sum(axis=1)):
        raise RuntimeError("Simulation goals do not balance")
    if not np.array_equal(points.sum(axis=1), 3 * 380 - draws + point_offsets.sum()):
        raise RuntimeError("Simulation points do not balance")
    goal_difference = goals_for - goals_against
    position_counts = np.zeros((len(teams), len(teams)))
    qualification = (
        {
            key: np.zeros(len(teams))
            for key in ("champions_league", "europa_league", "conference_league")
        }
        if europe is not None
        else {}
    )
    season = (played[0].fixture if played else remaining[0]).season_id
    use_head_to_head = int(season[:4]) >= 2019
    unresolved_count, head_to_head_count = 0, 0
    for sample in range(simulations):
        order, ties, unresolved, used_h2h = rank_table(
            teams,
            points[sample],
            goal_difference[sample],
            goals_for[sample],
            head_points[sample],
            head_away[sample],
            rng,
            head_to_head=use_head_to_head,
            europe=europe,
        )
        unresolved_count += unresolved
        head_to_head_count += used_h2h
        weights = np.eye(len(teams))
        for start, end in ties:
            weights[start:end, start:end] = 1 / (end - start)
        position_counts[order] += weights
        if europe is not None:
            for competition, qualified in european_places(
                [teams[i] for i in order], europe
            ).items():
                for team in qualified & team_index.keys():
                    qualification[competition][team_index[team]] += 1

    def distribution(values: np.ndarray) -> dict[str, float]:
        outcomes, counts = np.unique(values, return_counts=True)
        return {
            str(int(value)): float(count / simulations)
            for value, count in zip(outcomes, counts, strict=True)
        }

    rows = []
    for index, team in enumerate(teams):
        positions = position_counts[index] / simulations
        row = {
            "team_id": team,
            "mean_position": float(positions @ np.arange(1, len(teams) + 1)),
            "position_probabilities": list(positions),
            "mean_points": float(points[:, index].mean()),
            "points_quantiles_05_50_95": list(np.quantile(points[:, index], [0.05, 0.5, 0.95])),
            "points_distribution": distribution(points[:, index]),
            "mean_goal_difference": float(goal_difference[:, index].mean()),
            "goal_difference_distribution": distribution(goal_difference[:, index]),
            "title_probability": float(positions[0]),
            "top_four_probability": float(positions[:4].sum()),
            "top_five_probability": float(positions[:5].sum()),
            "relegation_probability": float(positions[-3:].sum()),
        }
        if europe is not None:
            row["conditional_europe_probabilities"] = {
                key: float(values[index] / simulations) for key, values in qualification.items()
            }
        rows.append(row)
    return {
        "season_id": season,
        "as_of": str(as_of),
        "results_observed_at": results_observed_at.isoformat() if results_observed_at else None,
        "simulations": simulations,
        "seed": seed,
        "played_matches": len(played),
        "remaining_matches": len(remaining),
        "state_uncertainty": "posterior" if states is not None else "fixed",
        "future_state_evolution": bool(getattr(states, "evolves_future_states", False)),
        "teams": rows,
        "unseen_teams": sorted(unknown_teams),
        "point_adjustments": adjustments,
        "head_to_head_applied_rate": head_to_head_count / simulations,
        "unresolved_decisive_tie_rate": unresolved_count / simulations,
        "assumptions": [
            (
                "One dynamics specification and current joint state per path; calendar-time "
                "latent transitions and independent match tempo shocks continue through fixtures. "
                "Simulated scores do not update the sampled latent states."
                if getattr(states, "evolves_future_states", False)
                else "One joint posterior state per season path, reused across fixtures. "
                "Includes strength uncertainty and match randomness; no future state evolution."
                if states is not None
                else "Fixed fitted team strengths; independent match outcomes "
                "conditional on fitted state."
            ),
            (
                "Captured full-time results are fixed, including today; fitting excludes today. "
                "Unscheduled dates are placeholders used only for fixed-strength simulation."
                if results_observed_at
                else "No future result labels used. "
                "Historical fixture dates are retrospectively recorded."
            ),
            "Nondecisive shared positions split mass across occupied ranks for reporting.",
            "Unresolved decisive ties assume equal playoff chances; playoff model not estimated.",
            "Points adjustments include only supplied sanctions known at the cutoff.",
        ]
        + (
            [
                f"European qualification is conditional on scenario: {europe.name}.",
                "Scenario assumes no extra English UEFA titleholders or eligibility exclusions.",
            ]
            if europe
            else ["Top-four/five probabilities are table positions, not European qualification."]
        ),
        "europe_scenario": None
        if europe is None
        else {
            "name": europe.name,
            "champions_league_places": europe.champions_league_places,
            "fa_cup_winner": europe.fa_cup_winner,
            "efl_cup_winner": europe.efl_cup_winner,
        },
    }
