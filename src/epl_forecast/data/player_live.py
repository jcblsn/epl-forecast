"""Immutable current player histories, available only from their collection timestamps."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.live import fpl_teams, read_live_snapshot, timestamp
from epl_forecast.data.players import normalize_player_matches
from epl_forecast.data.sources import SourceAccessError, download
from epl_forecast.data.squads import ROLES
from epl_forecast.storage import file_hash, json_bytes, write_immutable


def capture_player_histories(snapshot: Path, root: Path, workers=4):
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("Player capture workers must be between one and eight")
    parent = read_live_snapshot(snapshot)
    bootstrap = json.loads((snapshot / "fpl_bootstrap.json").read_text())
    elements = sorted(p["id"] for p in bootstrap["elements"] if p["element_type"] in range(1, 5))
    if any(type(i) is not int or i < 1 for i in elements) or len(set(elements)) != len(elements):
        raise ValueError("Invalid snapshot player element IDs")
    started = datetime.now(UTC)
    if timestamp(parent["completed_at"]) > started:
        raise ValueError("Cannot capture histories against a future snapshot")
    directory = root / started.strftime("%Y-%m-%dT%H%M%S.%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "season_id": parent["season_id"],
        "snapshot": str(snapshot.resolve()),
        "snapshot_manifest_sha256": file_hash(snapshot / "manifest.json"),
        "started_at": started.isoformat(),
        "requested_elements": elements,
        "files": [],
        "errors": [],
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        requests = [
            (
                i,
                pool.submit(
                    download, f"https://fantasy.premierleague.com/api/element-summary/{i}/"
                ),
            )
            for i in elements
        ]
        for number, (element, request) in enumerate(requests, 1):
            try:
                payload, metadata = request.result()
                decoded = json.loads(payload)
                if not isinstance(decoded.get("history"), list):
                    raise ValueError("Player summary has no history list")
            except (SourceAccessError, OSError, ValueError) as error:
                manifest["errors"].append({"element": element, "error": str(error)})
            else:
                name = f"{element}.json"
                write_immutable(directory / name, payload)
                manifest["files"].append({"element": element, "name": name, **metadata})
            if number % 50 == 0:
                print(f"Captured player histories {number}/{len(elements)}", flush=True)
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    write_immutable(directory / "manifest.json", json_bytes(manifest))
    return directory


def load_captured_player_histories(directory: Path, snapshot: Path | None = None):
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported player capture schema")
    snapshot = snapshot or Path(manifest["snapshot"])
    parent = read_live_snapshot(snapshot)
    if (
        file_hash(snapshot / "manifest.json") != manifest["snapshot_manifest_sha256"]
        or parent["season_id"] != manifest["season_id"]
    ):
        raise ValueError("Player capture does not match parent snapshot")
    started, completed = (timestamp(manifest[k]) for k in ("started_at", "completed_at"))
    if not timestamp(parent["completed_at"]) <= started <= completed:
        raise ValueError("Player capture timestamps are inconsistent")
    bootstrap = json.loads((snapshot / "fpl_bootstrap.json").read_text())
    mapping, _ = fpl_teams(bootstrap)
    players = {p["id"]: p for p in bootstrap["elements"] if p["element_type"] in range(1, 5)}
    if sorted(players) != manifest["requested_elements"]:
        raise ValueError("Player capture requested IDs disagree with snapshot")
    fixtures = json.loads((snapshot / "fpl_fixtures.json").read_text())
    completed_fixtures = {
        f["id"]: f for f in fixtures if f["finished"] or f["finished_provisional"]
    }
    seen, errors = set(), {e["element"] for e in manifest["errors"]}
    rows, sources, deferred = [], {}, 0
    for entry in manifest["files"]:
        element = entry["element"]
        if element not in players or element in seen or entry["name"] != f"{element}.json":
            raise ValueError("Unexpected or duplicate player history file")
        seen.add(element)
        observed = timestamp(entry["retrieved_at"])
        if not started <= observed <= completed:
            raise ValueError("Player observation outside capture interval")
        path = directory / entry["name"]
        if path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError("Player history checksum mismatch")
        player = players[element]
        for number, raw in enumerate(json.loads(path.read_text())["history"], 1):
            if raw.get("element", element) != element:
                raise ValueError("Player history element disagrees with endpoint")
            if raw["fixture"] not in completed_fixtures:
                deferred += 1
                continue
            fixture = completed_fixtures[raw["fixture"]]
            if timestamp(raw["kickoff_time"]) != timestamp(fixture["kickoff_time"]):
                raise ValueError("Player history kickoff disagrees with snapshot fixture")
            if timestamp(raw["kickoff_time"]) >= observed:
                raise ValueError("Player outcome cannot predate kickoff")
            if (raw["team_h_score"], raw["team_a_score"]) != (
                fixture["team_h_score"],
                fixture["team_a_score"],
            ):
                raise ValueError("Player history score disagrees with snapshot fixture")
            key = str(element), str(raw["fixture"])
            if key in sources:
                raise ValueError("Duplicate captured player fixture")
            sources[key] = (entry, number)
            rows.append(
                {
                    **{k: "" if v is None else str(v) for k, v in raw.items()},
                    "element": str(element),
                    "name": player["web_name"],
                    "position": ROLES[player["element_type"] - 1],
                }
            )
    if seen & errors or seen | errors != set(players):
        raise ValueError("Player capture must account for every requested endpoint")
    metadata = [{k: "" if v is None else str(v) for k, v in p.items()} for p in players.values()]
    fixture_rows = [{k: "" if v is None else str(v) for k, v in f.items()} for f in fixtures]
    season = f"{parent['season_id'][:4]}-{parent['season_id'][-2:]}"
    normalized, audit = normalize_player_matches(
        season,
        rows,
        metadata,
        {str(k): v for k, v in mapping.items()},
        file_hash(directory / "manifest.json"),
        fixture_rows,
    )
    for row in normalized:
        entry, number = sources[row["fpl_element_id"], row["fpl_fixture_id"]]
        row["source_sha256"], row["source_row"] = entry["sha256"], number
        row["historical_observed_at"] = entry["retrieved_at"]
    return normalized, {
        "capture": str(directory),
        "manifest_sha256": file_hash(directory / "manifest.json"),
        "completed_at": manifest["completed_at"],
        "errors": manifest["errors"],
        "deferred_rows_after_parent_snapshot": deferred,
        "audit": audit,
    }
