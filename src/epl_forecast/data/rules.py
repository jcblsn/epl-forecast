import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class LeagueRules:
    ranking: str
    relegated: int = 3
    automatic_promotion: int = 0
    playoff_end: int = 0


def league_rules(competition: str, season: str) -> LeagueRules:
    if competition == "eng-championship":
        return LeagueRules(
            "efl", automatic_promotion=2, playoff_end=8 if int(season[:4]) >= 2026 else 6
        )
    if competition == "eng-premier-league":
        return LeagueRules("pl_head_to_head" if int(season[:4]) >= 2019 else "shared")
    raise ValueError(f"Unsupported league rules: {competition}")


def historical_adjustments(season: str, as_of: date) -> list[dict]:
    events = json.loads(Path(__file__).with_name("pl_adjustments.json").read_text())
    return [
        event
        for event in events
        if event["season_id"] == season and date.fromisoformat(event["known_on"]) <= as_of
    ]
