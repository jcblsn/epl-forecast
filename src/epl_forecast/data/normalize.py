import csv
import io
import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from epl_forecast import __version__
from epl_forecast.data.sources import COMPETITIONS, csv_rows, read_snapshot
from epl_forecast.schema import Fixture, Match, fixture_id
from epl_forecast.storage import file_hash, write_json

TEAM_FILE = Path(__file__).with_name("teams.csv")
MATCH_FIELDS = [
    "match_id",
    "competition_id",
    "season_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_goals",
    "away_goals",
    "outcome",
    "available_on",
    "source_sha256",
    "source_row",
    "source_time",
]
ODDS_FAMILIES = {
    "bet365_preclosing": ("B365H", "B365D", "B365A"),
    "betbrain_average_preclosing": ("BbAvH", "BbAvD", "BbAvA"),
    "market_average_preclosing": ("AvgH", "AvgD", "AvgA"),
    "market_average_closing": ("AvgCH", "AvgCD", "AvgCA"),
}
ODDS_FIELDS = [
    "match_id",
    "family",
    "home_odds",
    "draw_odds",
    "away_odds",
    "source_columns",
    "source_sha256",
    "source_row",
    "observed_at",
]


def team_aliases(path: Path = TEAM_FILE) -> dict[str, str]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    aliases = {row["source_name"]: row["team_id"] for row in rows}
    if len(aliases) != len(rows) or any(not value for value in aliases.values()):
        raise ValueError("Invalid team alias registry")
    return aliases


def parse_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid source date: {value!r}")


def parse_score(value: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"Invalid goal count: {value!r}")
    return int(value)


def normalize_rows(
    payload: bytes, entry: dict, aliases: dict[str, str]
) -> tuple[list[Match], list[dict], dict]:
    fields, rows = csv_rows(payload)
    matches, odds = [], []
    quote_status = {family: Counter() for family in ODDS_FAMILIES}
    for row_number, row in rows:
        try:
            if row["Div"] != entry["division"]:
                raise ValueError("Division does not match the source manifest")
            for key in ("HomeTeam", "AwayTeam"):
                if row[key] not in aliases:
                    raise ValueError(f"Unknown team alias: {row[key]!r}; update teams.csv")
            home, away = aliases[row["HomeTeam"]], aliases[row["AwayTeam"]]
            played_on = parse_date(row["Date"])
            year = entry["season_start"]
            if not date(year, 7, 1) <= played_on < date(year + 1, 8, 1):
                raise ValueError("Match date falls outside its season")
            fixture = Fixture(
                fixture_id(entry["competition_id"], entry["season_id"], home, away),
                entry["competition_id"],
                entry["season_id"],
                played_on,
                home,
                away,
            )
            match = Match(
                fixture,
                parse_score(row["FTHG"]),
                parse_score(row["FTAG"]),
                entry["sha256"],
                row_number,
                row.get("Time", ""),
            )
            if match.outcome != row["FTR"]:
                raise ValueError("Full-time result disagrees with goals")
            matches.append(match)
            for family, columns in ODDS_FAMILIES.items():
                if any(not row.get(column) for column in columns):
                    quote_status[family]["missing"] += 1
                    continue
                try:
                    values = [float(row[column]) for column in columns]
                    valid = all(math.isfinite(value) and value > 1 for value in values)
                except ValueError:
                    valid = False
                if not valid:
                    quote_status[family]["invalid"] += 1
                    continue
                quote_status[family]["valid"] += 1
                odds.append(
                    dict(
                        zip(
                            ODDS_FIELDS,
                            [
                                fixture.match_id,
                                family,
                                *values,
                                ";".join(columns),
                                entry["sha256"],
                                row_number,
                                "",
                            ],
                            strict=True,
                        )
                    )
                )
        except ValueError as error:
            raise ValueError(
                f"{entry['season_id']} {entry['division']} row {row_number}: {error}"
            ) from error

    validate_unique(matches)
    teams = {team for m in matches for team in (m.fixture.home_team_id, m.fixture.away_team_id)}
    expected_teams = COMPETITIONS[entry["division"]]["teams"]
    if entry["division"] == "E0" and entry["season_start"] < 1995:
        expected_teams = 22
    n = len(matches)
    home_mean = sum(m.home_goals for m in matches) / n
    away_mean = sum(m.away_goals for m in matches) / n
    audit = {
        "season_id": entry["season_id"],
        "division": entry["division"],
        "matches": n,
        "teams": len(teams),
        "expected_teams": expected_teams,
        "expected_matches": expected_teams * (expected_teams - 1),
        "complete": len(teams) == expected_teams and n == expected_teams * (expected_teams - 1),
        "date_min": min(m.fixture.match_date for m in matches).isoformat(),
        "date_max": max(m.fixture.match_date for m in matches).isoformat(),
        "source_sha256": entry["sha256"],
        "columns": [f for f in fields if f],
        "missing_by_column": {f: sum(not row.get(f) for _, row in rows) for f in fields if f},
        "odds": {family: dict(counts) for family, counts in quote_status.items()},
        "outcomes": dict(Counter(m.outcome for m in matches)),
        "mean_home_goals": home_mean,
        "mean_away_goals": away_mean,
        "variance_home_goals": sum((m.home_goals - home_mean) ** 2 for m in matches) / n,
        "variance_away_goals": sum((m.away_goals - away_mean) ** 2 for m in matches) / n,
        "goal_covariance": sum(
            (m.home_goals - home_mean) * (m.away_goals - away_mean) for m in matches
        )
        / n,
        "score_0_0": sum(m.home_goals == m.away_goals == 0 for m in matches),
    }
    return matches, odds, audit


def validate_unique(matches: list[Match]) -> None:
    counts = Counter(m.fixture.match_id for m in matches)
    duplicates = [key for key, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate fixture IDs: {duplicates[:3]}")


def match_record(match: Match) -> dict:
    return {
        **asdict(match.fixture),
        "match_date": match.fixture.match_date.isoformat(),
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "outcome": match.outcome,
        "available_on": match.available_on.isoformat(),
        "source_sha256": match.source_sha256,
        "source_row": match.source_row,
        "source_time": match.source_time,
    }


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stream.getvalue())


def normalize_snapshot(root: Path, snapshot_path: Path, output: Path) -> dict:
    snapshot = read_snapshot(snapshot_path)
    aliases = team_aliases()
    matches, odds, coverage = [], [], []
    for entry in snapshot["files"]:
        path = root / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Raw checksum mismatch: {path}")
        normalized, quotes, audit = normalize_rows(path.read_bytes(), entry, aliases)
        matches.extend(normalized)
        odds.extend(quotes)
        coverage.append(audit)
    validate_unique(matches)
    matches.sort(key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    odds.sort(key=lambda quote: (quote["match_id"], quote["family"]))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "matches.csv", MATCH_FIELDS, [match_record(m) for m in matches])
    write_csv(output / "odds.csv", ODDS_FIELDS, odds)
    write_json(output / "coverage.json", {"schema_version": 1, "seasons": coverage})
    manifest = {
        "schema_version": 1,
        "normalizer_version": __version__,
        "snapshot_sha256": file_hash(snapshot_path),
        "aliases_sha256": file_hash(TEAM_FILE),
        "matches": len(matches),
        "odds_quotes": len(odds),
        "files": {
            name: file_hash(output / name) for name in ("matches.csv", "odds.csv", "coverage.json")
        },
        "availability_policy": "result available the next calendar day; date batches",
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def load_processed(directory: Path) -> tuple[list[Match], list[dict], dict]:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported processed schema")
    for name in ("matches.csv", "odds.csv", "coverage.json"):
        if file_hash(directory / name) != manifest["files"][name]:
            raise ValueError(f"Processed checksum mismatch: {name}; normalize the snapshot again")
    matches = []
    with (directory / "matches.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            fixture = Fixture(
                row["match_id"],
                row["competition_id"],
                row["season_id"],
                date.fromisoformat(row["match_date"]),
                row["home_team_id"],
                row["away_team_id"],
            )
            match = Match(
                fixture,
                parse_score(row["home_goals"]),
                parse_score(row["away_goals"]),
                row["source_sha256"],
                int(row["source_row"]),
                row["source_time"],
            )
            if match.outcome != row["outcome"] or str(match.available_on) != row["available_on"]:
                raise ValueError("Processed outcome or availability mismatch")
            matches.append(match)
    validate_unique(matches)
    with (directory / "odds.csv").open(newline="") as stream:
        odds = list(csv.DictReader(stream))
    return matches, odds, manifest
