"""Canonical current league state used by forecast export."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from epl_forecast.datasets import Dataset, timestamp
from epl_forecast.schema import Fixture

LONDON = ZoneInfo("Europe/London")


@dataclass
class LiveSeason:
    season_id: str
    observed_at: datetime
    teams: dict[str, str]
    played: list
    remaining: list
    details: dict
    manifest: dict
    results_crosschecked: int = 0
    competition_id: str = "eng-premier-league"


def load_live_season(root=Path("data"), cutoff=None, competition="eng-premier-league", season=None):
    cutoff = timestamp(cutoff) if cutoff else datetime.now(UTC)
    year = cutoff.year - (cutoff.month < 7)
    season = season or f"{year}-{year + 1}"
    data = Dataset(root, cutoff)
    try:
        records = [
            r
            for r in data.fixtures()
            if r["competition_id"] == competition
            and r["season_id"] == season
            and r["stage"] == "regular"
        ]
        if not records:
            raise ValueError("No captured fixtures for the selected league and season")
        inventory_times = [
            timestamp(m["request"]["retrieved_at"])
            for m in data.manifests
            if m["request"]["context"].get("endpoint") == "fixtures"
            and m["request"]["context"].get("league")
            == (39 if competition == "eng-premier-league" else 40)
            and m["request"]["context"].get("season") == int(season[:4])
        ]
        latest = (
            max(inventory_times) if inventory_times else min(r["retrieved_at"] for r in records)
        )
        names = {r["team_id"]: r["name"] for r in data.rows("SELECT * FROM teams")}
        teams = {
            t: names.get(t, t.replace("-", " ").title())
            for r in records
            for t in (r["home_team_id"], r["away_team_id"])
        }
        matches = {m.fixture.match_id: m for m in data.matches()}
        played, remaining, details = [], [], {}
        for r in records:
            key = r["match_id"]
            finished = r["status"] == "finished"
            if finished:
                played.append(matches[key])
            else:
                day = r["match_date"] or cutoff.astimezone(LONDON).date()
                remaining.append(
                    Fixture(key, competition, season, day, r["home_team_id"], r["away_team_id"])
                )
            status = r["status"]
            if not finished and (r["kickoff_time"] is None or status == "postponed"):
                status = "unscheduled"
            elif status == "scheduled" and r["kickoff_time"] <= cutoff:
                status = "awaiting_result"
            details[key] = {
                "match_id": key,
                "home_team_id": r["home_team_id"],
                "away_team_id": r["away_team_id"],
                "status": status,
                "kickoff_time": r["kickoff_time"].isoformat() if r["kickoff_time"] else None,
                "match_date": str(r["match_date"]) if r["match_date"] else None,
                "home_goals": r["home_goals"],
                "away_goals": r["away_goals"],
                "started": status in ("finished", "in_progress", "awaiting_result"),
            }
        files = [
            {
                "name": m["request"]["provider"],
                "retrieved_at": m["request"]["retrieved_at"],
                "sha256": m["request"]["source_sha256"],
            }
            for m in data.manifests
        ]
        return LiveSeason(
            season,
            cutoff,
            teams,
            played,
            remaining,
            details,
            {
                "files": files,
                "errors": [],
                "data": data.provenance(),
                "fixtures_retrieved_at": latest.isoformat(),
            },
            competition_id=competition,
        )
    finally:
        data.close()
