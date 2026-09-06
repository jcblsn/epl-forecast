"""Pinned provider-specific EPL xG observations, reconciled to canonical results."""

import csv
import gzip
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.normalize import TEAM_FILE, team_aliases
from epl_forecast.data.sources import download, season_name
from epl_forecast.schema import Match, fixture_id
from epl_forecast.storage import file_hash, json_bytes, sha256_bytes, write_immutable

PROVIDER = "understat"
AVAILABILITY = "retrospective; assumed next calendar day, original publication unverified"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://understat.com/"}


def source_url(year: int) -> str:
    if not 2014 <= year <= 2098:
        raise ValueError("Understat EPL seasons start at 2014")
    return f"https://understat.com/getLeagueData/EPL/{year}"


def parse_payload(payload: bytes) -> dict:
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get("dates"), list) or not data["dates"]:
        raise ValueError("Understat response lacks nonempty dates data")
    return data


def fetch_snapshot(root: Path, manifest_path: Path, start=2014, end=2025) -> dict:
    years = list(range(start, end + 1))
    if not years:
        raise ValueError("Specify an ordered season range")
    for year in years:
        source_url(year)
    existing = manifest_path.exists()
    manifest = (
        json.loads(manifest_path.read_text())
        if existing
        else {"schema_version": 1, "provider": PROVIDER, "files": []}
    )
    if manifest.get("schema_version") != 1 or manifest.get("provider") != PROVIDER:
        raise ValueError("Unsupported Understat snapshot")
    if existing and [e["season_start"] for e in manifest["files"]] != years:
        raise ValueError("Pinned Understat season range differs from request")
    for index, year in enumerate(years):
        url = source_url(year)
        if existing:
            entry = manifest["files"][index]
            expected = f"raw/understat/{year}/{entry['sha256']}.bin"
            if entry["url"] != url or entry["path"] != expected:
                raise ValueError("Unexpected Understat source path or URL")
            path = root / expected
            if path.exists():
                payload = path.read_bytes()
            else:
                payload, _ = download(url, headers=HEADERS)
            if sha256_bytes(payload) != entry["sha256"] or len(payload) != entry["bytes"]:
                raise ValueError(
                    "Understat source changed; restore pinned bytes or use a new manifest"
                )
            parse_payload(payload)
            write_immutable(path, payload)
        else:
            payload, metadata = download(url, headers=HEADERS)
            parse_payload(payload)
            path = root / f"raw/understat/{year}/{metadata['sha256']}.bin"
            write_immutable(path, payload)
            write_immutable(path.with_suffix(".metadata.json"), json_bytes(metadata))
            manifest["files"].append(
                {
                    "season_start": year,
                    "path": path.relative_to(root).as_posix(),
                    **{k: metadata[k] for k in ("url", "sha256", "bytes", "retrieved_at")},
                }
            )
        print(f"Pinned Understat {season_name(year)}", flush=True)
    write_immutable(manifest_path, json_bytes(manifest))
    return manifest


def provider_aliases() -> dict[str, str]:
    aliases = team_aliases()
    with TEAM_FILE.open(newline="") as stream:
        aliases.update({r["team_name"]: r["team_id"] for r in csv.DictReader(stream)})
    aliases.update(
        {
            "Newcastle United": "newcastle-united",
            "West Bromwich Albion": "west-bromwich-albion",
            "Hull City": "hull-city",
            "Stoke City": "stoke-city",
            "Swansea City": "swansea-city",
            "Norwich City": "norwich-city",
            "Cardiff City": "cardiff-city",
        }
    )
    return aliases


def reconcile(payload: bytes, year: int, matches: list[Match], source_hash: str):
    if sha256_bytes(payload) != source_hash:
        raise ValueError("Understat payload checksum mismatch")
    data = parse_payload(payload)
    season = season_name(year)
    canonical = {
        m.fixture.match_id: m
        for m in matches
        if m.fixture.season_id == season and m.fixture.competition_id == "eng-premier-league"
    }
    aliases = provider_aliases()
    records, issues, seen, source_ids = [], [], set(), set()
    unfinished = 0
    corrections = {
        (r["source_sha256"], r["source_match_id"]): r
        for r in json.loads(Path(__file__).with_name("understat_date_corrections.json").read_text())
    }
    corrected_dates = []
    for row in data["dates"]:
        if row.get("isResult") is False:
            unfinished += 1
            continue
        try:
            if row.get("isResult") is not True:
                raise ValueError("Unrecognized result flag")
            source_id = str(row["id"])
            if source_id in source_ids:
                raise ValueError("Duplicate provider match ID")
            source_ids.add(source_id)
            home, away = (aliases[row[side]["title"]] for side in ("h", "a"))
            key = fixture_id("eng-premier-league", season, home, away)
            if key in seen:
                raise ValueError("Duplicate canonical fixture")
            seen.add(key)
            match = canonical[key]
            day = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").date()
            if day != match.fixture.match_date:
                correction = corrections.get((source_hash, source_id))
                if correction is None or (
                    correction["source_datetime"] != row["datetime"]
                    or correction["match_id"] != key
                    or correction["canonical_date"] != str(match.fixture.match_date)
                ):
                    raise ValueError("Date mismatch")
                day = match.fixture.match_date
                corrected_dates.append(correction)
            goals = tuple(int(row["goals"][side]) for side in ("h", "a"))
            if goals != (match.home_goals, match.away_goals):
                raise ValueError("Score mismatch")
            xg = tuple(float(row["xG"][side]) for side in ("h", "a"))
            if any(not math.isfinite(x) or x < 0 for x in xg):
                raise ValueError("xG must be finite and nonnegative")
            records.append(
                {
                    "match_id": key,
                    "season_id": season,
                    "match_date": day.isoformat(),
                    "home_team_id": home,
                    "away_team_id": away,
                    "home_goals": goals[0],
                    "away_goals": goals[1],
                    "home_xg": xg[0],
                    "away_xg": xg[1],
                    "provider": PROVIDER,
                    "source_match_id": source_id,
                    "source_sha256": source_hash,
                    "source_datetime": row["datetime"],
                    "available_on": str(match.available_on),
                    "availability_basis": AVAILABILITY,
                }
            )
        except (KeyError, ValueError, TypeError) as error:
            issues.append({"source_match_id": row.get("id"), "error": str(error)})
    missing = sorted(set(canonical) - {r["match_id"] for r in records})
    return records, {
        "season_id": season,
        "canonical_matches": len(canonical),
        "reconciled": len(records),
        "unfinished": unfinished,
        "date_corrections": corrected_dates,
        "issues": issues,
        "missing_canonical": missing,
        "zero_xg_sides": sum(r[k] == 0 for r in records for k in ("home_xg", "away_xg")),
        "player_summary_rows": len(data.get("players", [])),
    }


def audit_snapshot(root: Path, manifest: dict, matches: list[Match]):
    records, reports = [], []
    for entry in manifest["files"]:
        rows, report = reconcile(
            (root / entry["path"]).read_bytes(), entry["season_start"], matches, entry["sha256"]
        )
        records.extend(rows)
        reports.append(report)
    return records, {
        "provider": PROVIDER,
        "audited_at": datetime.now(UTC).isoformat(),
        "semantics": "Understat match xG, including penalties; not FPL xG or npxG",
        "availability_basis": AVAILABILITY,
        "seasons": reports,
        "passed": all(
            not r["issues"] and not r["missing_canonical"] and r["reconciled"] == 380
            for r in reports
        ),
        "source_hashes": {e["path"]: file_hash(root / e["path"]) for e in manifest["files"]},
    }
