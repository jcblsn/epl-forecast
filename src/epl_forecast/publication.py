"""The compact derived surface that may leave this machine.

A published document is built only from model output: probabilities, season
distributions, event masses, timestamps and model identity. Provider payloads,
captured odds, request records, local file hashes and player tables stay in the
private archive. `configs/publication.toml` declares the allowlist, every
document is assembled from it by construction, and `check_publishable` re-checks
the assembled result so a careless addition fails loudly instead of shipping.
"""

import json
import re
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from epl_forecast.datasets import timestamp
from epl_forecast.storage import json_bytes, write_immutable, write_json

POLICY_PATH = Path("configs/publication.toml")
MINIMUM_SIMULATIONS = 1000
DIGEST = re.compile(r"\b[0-9a-f]{32,}\b")
TEAM_FIELDS = (
    "team_id",
    "played",
    "current_points",
    "mean_points",
    "median_points",
    "points_intervals",
    "points_quantiles_05_50_95",
    "mean_position",
    "median_position",
    "position_sd",
    "position_intervals",
    "mean_goal_difference",
)


def load_policy(path: Path = POLICY_PATH) -> dict:
    with Path(path).open("rb") as stream:
        policy = tomllib.load(stream)
    forbidden = policy["boundary"]["forbidden_key_substrings"]
    leaked = sorted(
        key
        for key in policy["surface"]["allowed_keys"]
        if any(substring in key for substring in forbidden)
    )
    if leaked:
        raise ValueError(f"Publication allowlist contradicts the boundary: {leaked}")
    return policy


def check_publishable(document, policy: dict) -> None:
    allowed = set(policy["surface"]["allowed_keys"])
    digest_keys = set(policy["surface"]["digest_keys"])
    forbidden = policy["boundary"]["forbidden_key_substrings"]
    patterns = [re.compile(p) for p in policy["boundary"]["forbidden_value_patterns"]]

    def walk(node, trail, key=None):
        if isinstance(node, dict):
            for name, value in node.items():
                if any(substring in name for substring in forbidden):
                    raise ValueError(f"Private key on the published surface: {trail}.{name}")
                if name not in allowed and not _is_open_map(trail):
                    raise ValueError(f"Key is not on the publication allowlist: {trail}.{name}")
                walk(value, f"{trail}.{name}", name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]", key)
        elif isinstance(node, str):
            for pattern in patterns:
                if pattern.search(node):
                    raise ValueError(f"Private value on the published surface: {trail} ({node!r})")
            if DIGEST.search(node) and key not in digest_keys:
                raise ValueError(f"Unexpected digest on the published surface: {trail}")

    walk(document, "$")


def _is_open_map(trail: str) -> bool:
    return trail.endswith(
        (".points_distribution", ".events", ".summary", ".points_intervals", ".position_intervals")
    )


def probability(value) -> float:
    return round(float(value), 6)


def _number(value):
    return round(float(value), 3) if isinstance(value, float) else value


def _compact(value):
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    return _number(value)


def _distribution(mapping: dict) -> dict:
    kept = {key: probability(value) for key, value in mapping.items() if float(value) >= 5e-7}
    return {key: kept[key] for key in sorted(kept, key=int)}


def derive_forecast(
    forecast: dict,
    run: dict,
    snapshot_id: str,
    verification: dict | None = None,
    horizon_days: int = 21,
) -> dict:
    simulation = forecast["simulation"]
    if simulation is None:
        raise ValueError(
            f"Refusing to publish a forecast without a season projection: {snapshot_id}"
        )
    if simulation["simulations"] < MINIMUM_SIMULATIONS:
        raise ValueError(
            f"Refusing to publish {simulation['simulations']} simulated paths; the product floor is {MINIMUM_SIMULATIONS}"
        )
    names = forecast["team_names"]
    teams = []
    for row in sorted(simulation["teams"], key=lambda row: row["mean_position"]):
        teams.append(
            {
                **{field: _compact(row[field]) for field in TEAM_FIELDS},
                "name": names.get(row["team_id"], row["team_id"]),
                "position_probabilities": [probability(p) for p in row["position_probabilities"]],
                "points_distribution": _distribution(row["points_distribution"]),
                "events": {
                    key: probability(value)
                    for key, value in sorted(row.items())
                    if key.endswith("_probability")
                },
            }
        )
    matches = []
    horizon = timestamp(forecast["generated_at"]) + timedelta(days=horizon_days)
    for row in forecast["matches"]:
        if row["status"] != "scheduled" or not row["kickoff_time"]:
            continue
        if timestamp(row["kickoff_time"]) > horizon and not row["next_match_for_teams"]:
            continue
        assisted = row["market_assisted_probabilities"]
        published = {
            "match_id": row["match_id"],
            "kickoff_time": row["kickoff_time"],
            "match_date": row["match_date"],
            "home_team_id": row["home_team_id"],
            "away_team_id": row["away_team_id"],
            "status": row["status"],
            "p_home": probability(row["p_home"]),
            "p_draw": probability(row["p_draw"]),
            "p_away": probability(row["p_away"]),
            "market_assisted": None
            if assisted is None
            else {key: probability(assisted[key]) for key in ("p_home", "p_draw", "p_away")},
        }
        if row["next_match_for_teams"]:
            scores = row["score_distribution"]
            published["score_probabilities"] = {
                "home_rate": round(float(scores["home_rate"]), 6),
                "away_rate": round(float(scores["away_rate"]), 6),
                "omitted_probability": probability(scores["omitted_probability"]),
                "grid_home_rows_away_columns": [
                    [probability(cell) for cell in line]
                    for line in scores["grid_home_rows_away_columns"]
                ],
            }
        matches.append(published)
    document = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "competition_id": forecast["competition_id"],
        "competition_name": forecast["competition_name"],
        "season_id": forecast["season_id"],
        "generated_at": forecast["generated_at"],
        "state_observed_at": forecast["state_observed_at"],
        "model_results_cutoff": forecast["model_results_cutoff"],
        "state_uncertainty": forecast["state_uncertainty"],
        "simulations": simulation["simulations"],
        "match_horizon_days": horizon_days,
        "model": {
            "model_id": forecast["model"]["id"],
            "model_kind": forecast["model"]["kind"],
            "package_version": run.get("package_version"),
            "code_sha256": run.get("code_sha256"),
            "commit": run.get("execution", {}).get("commit"),
        },
        "teams": teams,
        "matches": matches,
        "verification": None
        if verification is None
        else {
            "checks": len(verification["checks"]),
            "failures": verification["failures"],
        },
    }
    document["model"] = {
        key: value for key, value in document["model"].items() if value is not None
    }
    return document


def snapshot_directory(site: Path, snapshot_id: str) -> Path:
    return Path(site) / "data" / "forecasts" / snapshot_id


def publish_document(site: Path, document: dict, policy: dict) -> Path:
    check_publishable(document, policy)
    target = (
        snapshot_directory(site, document["snapshot_id"]) / f"{document['competition_id']}.json"
    )
    write_immutable(target, json_bytes(document))
    return target


def rebuild_index(site: Path, policy: dict) -> dict:
    site = Path(site)
    root = site / "data" / "forecasts"
    snapshots = []
    for directory in sorted(p for p in root.glob("*") if p.is_dir()):
        competitions = []
        for path in sorted(directory.glob("*.json")):
            document = json.loads(path.read_text())
            competitions.append(
                {
                    "competition_id": document["competition_id"],
                    "competition_name": document["competition_name"],
                    "season_id": document["season_id"],
                    "model_id": document["model"]["model_id"],
                    "matches": len(document["matches"]),
                    "href": path.relative_to(site / "data").as_posix(),
                }
            )
            generated = document["generated_at"]
        if competitions:
            snapshots.append(
                {
                    "snapshot_id": directory.name,
                    "generated_at": generated,
                    "competitions": competitions,
                }
            )
    snapshots.sort(key=lambda row: row["snapshot_id"], reverse=True)
    index = {
        "schema_version": 1,
        "archived_at": datetime.now(UTC).isoformat(),
        "latest": snapshots[0]["snapshot_id"] if snapshots else None,
        "snapshots": snapshots,
    }
    check_publishable(index, policy)
    write_json(site / "data" / "index.json", index)
    return index


def published_documents(site: Path):
    for path in sorted((Path(site) / "data" / "forecasts").glob("*/*.json")):
        yield json.loads(path.read_text())
