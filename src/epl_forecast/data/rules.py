import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeagueRules:
    ranking: str
    relegated: int = 3
    automatic_promotion: int = 0
    playoff_end: int = 0

    @property
    def promotes(self) -> bool:
        return self.playoff_end > 0

    @property
    def playoff_places(self) -> int:
        return self.playoff_end - self.automatic_promotion


def league_rules(competition: str, season: str) -> LeagueRules:
    if competition == "eng-premier-league":
        return LeagueRules("pl_head_to_head" if int(season[:4]) >= 2019 else "shared")
    if competition == "eng-championship":
        return LeagueRules(
            "efl", automatic_promotion=2, playoff_end=8 if int(season[:4]) >= 2026 else 6
        )
    if competition == "eng-league-one":
        return LeagueRules("efl", relegated=4, automatic_promotion=2, playoff_end=6)
    if competition == "eng-league-two":
        return LeagueRules("efl", relegated=2, automatic_promotion=3, playoff_end=7)
    raise ValueError(f"Unsupported league rules: {competition}")


def reviewed_rules_evidence(competition: str, season: str) -> dict | None:
    entries = json.loads(Path(__file__).with_name("efl_rules_evidence.json").read_text())
    for evidence in entries:
        if (competition, season) == (evidence["competition_id"], evidence["season_id"]):
            return evidence
    return None
