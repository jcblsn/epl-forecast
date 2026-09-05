import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from epl_forecast.data.normalize import TEAM_FILE, normalize_rows, team_aliases
from epl_forecast.data.sources import SourceAccessError, download, season_name, source_url
from epl_forecast.schema import Fixture, Match, fixture_id
from epl_forecast.simulation import validate_schedule
from epl_forecast.storage import file_hash, json_bytes, write_immutable

LONDON = ZoneInfo("Europe/London")
COMPETITION = "eng-premier-league"


def live_sources(season_start: int) -> dict[str, str]:
    return {
        "fpl_bootstrap.json": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "fpl_fixtures.json": "https://fantasy.premierleague.com/api/fixtures/",
        "football_data_fixtures.csv": "https://football-data.co.uk/fixtures.csv",
        "football_data_E0.csv": source_url(season_start, "E0"),
        "football_data_E1.csv": source_url(season_start, "E1"),
    }


def capture_snapshot(root: Path, season_start: int) -> Path:
    sources = live_sources(season_start)
    started = datetime.now(UTC)
    directory = root / started.strftime("%Y-%m-%dT%H%M%S.%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "season_id": season_name(season_start),
        "started_at": started.isoformat(),
        "files": [],
        "errors": [],
    }
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        requests = [(name, url, pool.submit(download, url)) for name, url in sources.items()]
        for name, url, request in requests:
            try:
                payload, metadata = request.result()
            except (SourceAccessError, OSError) as error:
                manifest["errors"].append({"name": name, "url": url, "error": str(error)})
                print(f"Could not capture {name}: {error}", flush=True)
                continue
            write_immutable(directory / name, payload)
            manifest["files"].append({"name": name, **metadata})
            print(f"Captured {name} ({len(payload):,} bytes)", flush=True)
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    write_immutable(directory / "manifest.json", json_bytes(manifest))
    return directory


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Live timestamps must include a timezone")
    return parsed.astimezone(UTC)


def read_live_snapshot(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported live snapshot schema")
    season = int(manifest["season_id"][:4])
    if manifest["season_id"] != season_name(season):
        raise ValueError("Invalid live snapshot season")
    sources = live_sources(season)
    seen = set()
    started, completed = (timestamp(manifest[key]) for key in ("started_at", "completed_at"))
    if completed < started:
        raise ValueError("Snapshot completion predates its start")
    for entry in manifest["files"]:
        name = entry["name"]
        if name not in sources or name in seen:
            raise ValueError(f"Unexpected or duplicate snapshot file: {name}")
        seen.add(name)
        if not started <= timestamp(entry["retrieved_at"]) <= completed:
            raise ValueError("Source observation time falls outside snapshot capture")
        path = directory / name
        if path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError(f"Live snapshot checksum mismatch: {name}")
    required = {"fpl_bootstrap.json", "fpl_fixtures.json"}
    if not required <= seen:
        raise ValueError(f"Forecast requires captured sources: {sorted(required - seen)}")
    return manifest


@dataclass
class LiveSeason:
    season_id: str
    observed_at: datetime
    teams: dict[str, str]
    played: list[Match]
    remaining: list[Fixture]
    details: dict[str, dict]
    manifest: dict
    results_crosschecked: int


def fpl_teams(bootstrap: dict) -> tuple[dict[int, str], dict[str, str]]:
    aliases = team_aliases()
    with TEAM_FILE.open(newline="") as stream:
        registry = list(csv.DictReader(stream))
    aliases.update({row["team_name"]: row["team_id"] for row in registry})
    aliases.update({"Man Utd": "manchester-united", "Spurs": "tottenham-hotspur"})
    names = {row["team_id"]: row["team_name"] for row in registry}
    mapping = {}
    for team in bootstrap["teams"]:
        if team["name"] not in aliases:
            raise ValueError(f"Unknown FPL team alias: {team['name']!r}; update the team mapping")
        if type(team["id"]) is not int or team["id"] in mapping:
            raise ValueError("FPL team IDs must be distinct integers")
        mapping[team["id"]] = aliases[team["name"]]
    if len(mapping) != 20 or len(set(mapping.values())) != 20:
        raise ValueError("FPL schedule requires 20 distinct canonical teams")
    return mapping, {team: names[team] for team in sorted(mapping.values())}


def load_live_season(directory: Path) -> LiveSeason:
    manifest = read_live_snapshot(directory)
    season = manifest["season_id"]
    observed = timestamp(manifest["completed_at"])
    as_of = observed.astimezone(LONDON).date()
    bootstrap = json.loads((directory / "fpl_bootstrap.json").read_bytes())
    mapping, teams = fpl_teams(bootstrap)
    first_deadline = min(timestamp(event["deadline_time"]) for event in bootstrap["events"])
    if first_deadline.astimezone(LONDON).date().year != int(season[:4]):
        raise ValueError("FPL bootstrap season differs from the requested season")
    fixtures = json.loads((directory / "fpl_fixtures.json").read_bytes())
    entries = {entry["name"]: entry for entry in manifest["files"]}
    source = entries["fpl_fixtures.json"]
    fixture_observed = timestamp(source["retrieved_at"])
    played, remaining, details = [], [], {}
    source_ids = set()
    for row in fixtures:
        if type(row["id"]) is not int or row["id"] in source_ids:
            raise ValueError("Duplicate or invalid FPL fixture ID")
        source_ids.add(row["id"])
        if row["team_h"] not in mapping or row["team_a"] not in mapping:
            raise ValueError("FPL fixture contains a team outside this season")
        home, away = mapping[row["team_h"]], mapping[row["team_a"]]
        kickoff = timestamp(row["kickoff_time"]) if row["kickoff_time"] else None
        match_date = kickoff.astimezone(LONDON).date() if kickoff else None
        for flag in ("started", "finished", "finished_provisional"):
            if row.get(flag) not in (True, False, None):
                raise ValueError(f"Invalid FPL status: {flag}")
        complete = row["finished"] or row["finished_provisional"]
        if complete:
            if kickoff is None or kickoff >= fixture_observed or not row["started"]:
                raise ValueError("FPL completed fixture has an inconsistent kickoff/status")
            if not row["finished"] and row["minutes"] < 90:
                raise ValueError("Provisional full-time result has fewer than 90 minutes")
            status = "finished" if row["finished"] else "finished_provisional"
        elif row["started"]:
            if kickoff is None or kickoff > fixture_observed:
                raise ValueError("FPL started fixture has an inconsistent kickoff")
            status = "in_progress"
        elif kickoff is None or (kickoff <= fixture_observed and row["event"] is None):
            status = "unscheduled"
        elif kickoff <= fixture_observed:
            status = "awaiting_result"
        else:
            status = "scheduled"
        if match_date and not int(season[:4]) <= match_date.year <= int(season[5:]):
            raise ValueError("FPL fixture date falls outside the snapshot season")
        # Fixed-strength models do not use future fixture dates; keep unknown dates null in exports.
        model_date = match_date if complete else max(match_date or as_of, as_of)
        fixture = Fixture(
            fixture_id(COMPETITION, season, home, away),
            COMPETITION,
            season,
            model_date,
            home,
            away,
        )
        if fixture.match_id in details:
            raise ValueError(f"Duplicate FPL ordered fixture: {fixture.match_id}")
        details[fixture.match_id] = {
            "match_id": fixture.match_id,
            "fpl_fixture_id": row["id"],
            "home_team_id": home,
            "away_team_id": away,
            "kickoff_time": kickoff.isoformat() if kickoff else None,
            "match_date": str(match_date) if match_date else None,
            "gameweek": row["event"],
            "status": status,
            "home_goals": row["team_h_score"] if complete else None,
            "away_goals": row["team_a_score"] if complete else None,
        }
        if complete:
            played.append(
                Match(
                    fixture,
                    row["team_h_score"],
                    row["team_a_score"],
                    source["sha256"],
                    row["id"],
                    kickoff.astimezone(LONDON).strftime("%H:%M"),
                )
            )
        else:
            remaining.append(fixture)
    validate_schedule(list(teams), played, remaining, as_of, results_observed_at=observed)
    checked = 0
    if "football_data_E0.csv" in entries:
        entry = entries["football_data_E0.csv"]
        payload = (directory / entry["name"]).read_bytes()
        if list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))):
            results, _, _ = normalize_rows(
                payload,
                {
                    **entry,
                    "division": "E0",
                    "competition_id": COMPETITION,
                    "season_start": int(season[:4]),
                    "season_id": season,
                },
                team_aliases(),
            )
            fpl_results = {match.fixture.match_id: match for match in played}
            for match in results:
                other = fpl_results.get(match.fixture.match_id)
                if other is None or (
                    match.fixture.match_date,
                    match.home_goals,
                    match.away_goals,
                ) != (other.fixture.match_date, other.home_goals, other.away_goals):
                    raise ValueError(
                        f"FPL / Football-Data result conflict: {match.fixture.match_id}"
                    )
                checked += 1
    return LiveSeason(season, observed, teams, played, remaining, details, manifest, checked)
