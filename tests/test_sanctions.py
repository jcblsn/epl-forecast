from datetime import UTC, date, datetime, timedelta

from epl_forecast.sanctions import SanctionRegistry, reviewed_adjustments
from epl_forecast.schema import Fixture, Match, fixture_id

COMPETITION = "eng-championship"
SEASON = "2021-2022"


def standings_row(team, rank, points, played, goal_difference, retrieved, updated=None):
    return {
        "competition_id": COMPETITION,
        "season_id": SEASON,
        "team_id": team,
        "rank": rank,
        "points": points,
        "played": played,
        "goal_difference": goal_difference,
        "retrieved_at": retrieved,
        "updated_at": updated or retrieved,
        "source_sha256": "0" * 64,
    }


def league(goals, season=SEASON, competition=COMPETITION):
    """A round robin between four clubs; ``goals`` gives each fixture's score in order."""
    teams = ["a", "b", "c", "d"]
    pairs = [(h, a) for h in teams for a in teams if h != a]
    return [
        Match(
            Fixture(
                fixture_id(competition, season, home, away),
                competition,
                season,
                date(2021, 8, 7) + timedelta(days=index),
                home,
                away,
            ),
            *goals[index],
        )
        for index, (home, away) in enumerate(pairs)
    ]


def points_and_difference(matches, team):
    points = difference = 0
    for match in matches:
        for side, scored, conceded in (
            (match.fixture.home_team_id, match.home_goals, match.away_goals),
            (match.fixture.away_team_id, match.away_goals, match.home_goals),
        ):
            if side == team:
                points += 3 if scored > conceded else 1 if scored == conceded else 0
                difference += scored - conceded
    return points, difference


def test_points_gap_against_a_matching_table_is_a_sanction():
    matches = league([(2, 0)] * 12)
    retrieved = datetime(2022, 6, 1, tzinfo=UTC)
    rows = []
    for rank, team in enumerate(["a", "b", "c", "d"], 1):
        team_points, team_difference = points_and_difference(matches, team)
        deduction = 6 if team == "a" else 0
        rows.append(
            standings_row(team, rank, team_points - deduction, 6, team_difference, retrieved)
        )
    registry = SanctionRegistry(rows, matches)
    derivation = registry.derivation(COMPETITION, SEASON)
    assert derivation["sanctioned_table_available"] is False  # four clubs, not a full season
    assert [(a["team_id"], a["points"]) for a in derivation["adjustments"]] == [("a", -6)]
    assert derivation["adjustments"][0]["observed_on"] == "2022-06-01"


def test_partial_snapshot_reports_the_prefix_it_describes_and_no_sanction():
    matches = league([(2, 0)] * 12)
    retrieved = datetime(2022, 6, 1, tzinfo=UTC)
    rows = []
    for rank, team in enumerate(["a", "b", "c", "d"], 1):
        played = [
            m
            for m in matches
            if team in (m.fixture.home_team_id, m.fixture.away_team_id)
            and m.fixture.match_date <= date(2021, 8, 12)
        ]
        points, difference = points_and_difference(played, team)
        rows.append(standings_row(team, rank, points, len(played), difference, retrieved))
    derivation = SanctionRegistry(rows, matches).derivation(COMPETITION, SEASON)
    assert not derivation["adjustments"]
    assert derivation["teams_unknown"] == 0
    assert derivation["sanctioned_table_available"] is False


def test_a_table_that_does_not_describe_the_archive_is_unknown_not_a_sanction():
    matches = league([(2, 0)] * 12)
    retrieved = datetime(2022, 6, 1, tzinfo=UTC)
    rows = []
    for rank, team in enumerate(["a", "b", "c", "d"], 1):
        points, difference = points_and_difference(matches, team)
        rows.append(standings_row(team, rank, points - 3, 6, difference + 5, retrieved))
    derivation = SanctionRegistry(rows, matches).derivation(COMPETITION, SEASON)
    assert not derivation["adjustments"]
    assert derivation["teams_unknown"] == 4
    assert all(row["resolution"].startswith("unknown:") for row in derivation["unknown"])


def test_retrospective_capture_is_knowable_to_no_in_season_cutoff():
    matches = league([(2, 0)] * 12)
    retrieved = datetime(2026, 9, 10, tzinfo=UTC)
    rows = []
    for rank, team in enumerate(["a", "b", "c", "d"], 1):
        points, difference = points_and_difference(matches, team)
        deduction = 6 if team == "a" else 0
        rows.append(standings_row(team, rank, points - deduction, 6, difference, retrieved))
    registry = SanctionRegistry(rows, matches)
    assert not registry.known_adjustments(COMPETITION, SEASON, date(2022, 5, 1))
    assert registry.known_adjustments(COMPETITION, SEASON, date(2026, 9, 10))


def test_reviewed_announcements_supersede_the_same_club_in_the_final_table():
    season, competition = "2023-2024", "eng-premier-league"
    reviewed = reviewed_adjustments(competition, season)
    assert {event["team_id"] for event in reviewed} == {"everton", "nottingham-forest"}
    assert sum(event["points"] for event in reviewed) == -12
    registry = SanctionRegistry([], [])
    known = registry.known_adjustments(competition, season, date(2024, 4, 9))
    assert sum(event["points"] for event in known) == -12
    assert {event["applies"] for event in known} == {"reviewed announcement"}
