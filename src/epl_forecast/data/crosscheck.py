import csv
import json
from pathlib import Path

from epl_forecast.data.normalize import TEAM_FILE, load_processed
from epl_forecast.data.sources import download
from epl_forecast.schema import fixture_id
from epl_forecast.storage import file_hash, json_bytes, sha256_bytes, write_immutable, write_json


def crosscheck_openfootball(data: Path, snapshot_path: Path, output: Path) -> dict:
    snapshot = json.loads(snapshot_path.read_text())
    path = Path(snapshot["path"])
    if not path.exists():
        payload, metadata = download(snapshot["url"])
        if sha256_bytes(payload) != snapshot["sha256"]:
            raise ValueError("OpenFootball checksum does not match the pinned source")
        write_immutable(path, payload)
        write_immutable(path.with_suffix(".metadata.json"), json_bytes(metadata))
    if file_hash(path) != snapshot["sha256"]:
        raise ValueError("OpenFootball raw checksum mismatch")
    matches, _, manifest = load_processed(data)
    season = "2024-2025"
    targets = {
        m.fixture.match_id: m
        for m in matches
        if m.fixture.season_id == season and m.fixture.competition_id == "eng-premier-league"
    }
    with TEAM_FILE.open(newline="") as stream:
        aliases = {
            row["team_name"].replace(" and ", " & "): row["team_id"]
            for row in csv.DictReader(stream)
        }
    other = {}
    for row in json.loads(path.read_text())["matches"]:
        home, away = (aliases[row[key].removesuffix(" FC")] for key in ("team1", "team2"))
        key = fixture_id("eng-premier-league", season, home, away)
        if key in other:
            raise ValueError(f"Duplicate OpenFootball fixture: {key}")
        other[key] = row
    common = sorted(targets.keys() & other.keys())
    score_mismatches, date_mismatches = [], []
    for key in common:
        match, row = targets[key], other[key]
        if [match.home_goals, match.away_goals] != row.get("score", {}).get("ft"):
            score_mismatches.append(key)
        if str(match.fixture.match_date) != row.get("date"):
            date_mismatches.append(key)
    report = {
        "season_id": season,
        "comparison": "Football-Data vs pinned OpenFootball public archive",
        "source": snapshot,
        "matches_sha256": manifest["files"]["matches.csv"],
        "compared_matches": len(common),
        "score_mismatches": score_mismatches,
        "date_mismatches": date_mismatches,
        "missing_from_openfootball": sorted(targets.keys() - other.keys()),
        "missing_from_primary": sorted(other.keys() - targets.keys()),
        "all_agree": len(common) == 380
        and not (score_mismatches or date_mismatches)
        and targets.keys() == other.keys(),
    }
    write_json(output, report)
    return report
