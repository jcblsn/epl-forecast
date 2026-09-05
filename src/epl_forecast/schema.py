from dataclasses import dataclass
from datetime import date, timedelta

OUTCOMES = ("H", "D", "A")


def fixture_id(competition: str, season: str, home: str, away: str) -> str:
    return ":".join((competition, season, home, away))


@dataclass(frozen=True)
class Fixture:
    match_id: str
    competition_id: str
    season_id: str
    match_date: date
    home_team_id: str
    away_team_id: str

    def __post_init__(self) -> None:
        try:
            start, end = (int(part) for part in self.season_id.split("-"))
        except (ValueError, AttributeError) as error:
            raise ValueError("Season IDs must use YYYY-YYYY") from error
        if end != start + 1 or self.season_id != f"{start:04d}-{end:04d}":
            raise ValueError("Season IDs must identify consecutive years")
        if type(self.match_date) is not date:
            raise ValueError("Fixture dates must have calendar-day precision")
        if not date(start, 7, 1) <= self.match_date < date(end, 8, 1):
            raise ValueError("Fixture date falls outside its season")
        if not self.home_team_id or not self.away_team_id:
            raise ValueError("Team IDs must be nonempty")
        if self.home_team_id == self.away_team_id:
            raise ValueError("A team cannot play itself")
        expected = fixture_id(
            self.competition_id, self.season_id, self.home_team_id, self.away_team_id
        )
        if self.match_id != expected:
            raise ValueError(f"Match ID does not match its fixture: {self.match_id}")


@dataclass(frozen=True)
class Match:
    fixture: Fixture
    home_goals: int
    away_goals: int
    source_sha256: str = ""
    source_row: int = 0
    source_time: str = ""

    def __post_init__(self) -> None:
        for goals in (self.home_goals, self.away_goals):
            if type(goals) is not int or goals < 0:
                raise ValueError("Goals must be nonnegative integers")

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "H"
        return "D" if self.home_goals == self.away_goals else "A"

    @property
    def available_on(self) -> date:
        return self.fixture.match_date + timedelta(days=1)


def validate_training(matches: list[Match], as_of: date) -> None:
    if not matches:
        raise ValueError("Training set is empty")
    if any(match.available_on > as_of for match in matches):
        raise ValueError("Training contains a result unavailable at the forecast cutoff")
    if len({match.fixture.competition_id for match in matches}) != 1:
        raise ValueError("These baselines require a single competition")
    if len({match.fixture.match_id for match in matches}) != len(matches):
        raise ValueError("Duplicate training matches")
