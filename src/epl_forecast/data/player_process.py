"""Explicit identity and role evidence for a future attacking-process player layer."""

import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from epl_forecast.data.squads import load_player_history
from epl_forecast.storage import file_hash


def normalized_name(value):
    value = unicodedata.normalize("NFKD", value.replace("_", " "))
    return " ".join(
        re.findall(r"[a-z]+", "".join(c for c in value if not unicodedata.combining(c)).lower())
    )


def process_role(position):
    if position == "GK":
        return "GK"
    if position in {"DC", "DL", "DR"}:
        return "DEF"
    if position.startswith("FW"):
        return "FWD"
    if position in {"MC", "MR", "ML", "DMC", "DMR", "DML", "AMC", "AMR", "AML"}:
        return "MID"
    if position == "Sub":
        return None
    raise ValueError(f"Unknown Understat role: {position}")


def identity_audit(sample_manifest, players_path, data_root=Path("data"), aliases=None):
    aliases = aliases or {}
    players = load_player_history(players_path)
    fpl = defaultdict(list)
    for row in players:
        fpl[row["match_id"], row["team_id"]].append(row)
    manifest = json.loads(sample_manifest.read_text())
    records, stable_codes = [], defaultdict(set)
    for entry in manifest["files"]:
        path = data_root / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Understat sample source hash mismatch")
        payload = path.read_bytes()
        data = json.loads(gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload)
        match = entry["match_id"]
        _, season, home, away = match.split(":")
        for side, team in [("h", home), ("a", away)]:
            candidates = fpl[match, team]
            for row in data["rosters"][side].values():
                name = aliases.get(str(row["player_id"]), row["player"])
                exact = [
                    p
                    for p in candidates
                    if normalized_name(p["player_name"]) == normalized_name(name)
                ]
                record = {
                    "match_id": match,
                    "team_id": team,
                    "season_id": season,
                    "understat_id": str(row["player_id"]),
                    "understat_name": row["player"],
                    "understat_role": row["position"],
                    "process_role": process_role(row["position"]),
                    "understat_minutes": int(row["time"]),
                    "understat_xg": float(row["xG"]),
                    "understat_xa": float(row["xA"]),
                    "understat_shots": int(row["shots"]),
                    "understat_source_sha256": entry["sha256"],
                    "status": "unresolved" if candidates else "no_fpl_fixture_coverage",
                }
                if len(exact) == 1:
                    p = exact[0]
                    record.update(
                        {
                            "status": "linked",
                            "method": "explicit_alias"
                            if str(row["player_id"]) in aliases
                            else "exact_normalized_name_and_fixture_team",
                            "fpl_player_code": p["fpl_player_code"],
                            "fpl_player_season_id": p["player_season_id"],
                            "fpl_name": p["player_name"],
                            "fpl_role": p["position"],
                            "fpl_source_sha256": p["source_sha256"],
                        }
                    )
                    if p["fpl_player_code"]:
                        stable_codes[str(row["player_id"])].add(p["fpl_player_code"])
                elif candidates:
                    record["candidate_names"] = sorted(
                        {p["player_name"] for p in candidates if int(p["minutes"] or 0) > 0}
                    )
                records.append(record)
    conflicts = {key: sorted(v) for key, v in stable_codes.items() if len(v) > 1}
    if conflicts:
        raise ValueError(f"Understat identity maps to conflicting stable FPL codes: {conflicts}")
    for row in records:
        if row["status"] != "unresolved" or row["understat_id"] not in stable_codes:
            continue
        codes = stable_codes[row["understat_id"]]
        candidates = [
            p for p in fpl[row["match_id"], row["team_id"]] if p["fpl_player_code"] in codes
        ]
        if len(candidates) == 1:
            p = candidates[0]
            row.update(
                {
                    "status": "linked",
                    "method": "stable_code_from_other_matched_fixture",
                    "fpl_player_code": p["fpl_player_code"],
                    "fpl_player_season_id": p["player_season_id"],
                    "fpl_name": p["player_name"],
                    "fpl_role": p["position"],
                    "fpl_source_sha256": p["source_sha256"],
                }
            )
            row.pop("candidate_names", None)
    for row in records:
        if row["status"] == "linked":
            row["role_disagrees"] = bool(
                row["process_role"] and row["fpl_role"] and row["process_role"] != row["fpl_role"]
            )
            if row["process_role"] is None and row["fpl_role"]:
                row["process_role"] = row["fpl_role"]
                row["role_source"] = "FPL season position; substitute role remains unobserved"
            else:
                row["role_source"] = "Understat match role; distinct from FPL season position"
    return {
        "inputs": {
            str(sample_manifest): file_hash(sample_manifest),
            str(players_path): file_hash(players_path),
        },
        "status_counts": dict(Counter(r["status"] for r in records)),
        "unique_understat_ids": len({r["understat_id"] for r in records}),
        "linked_understat_ids": len(
            {r["understat_id"] for r in records if r["status"] == "linked"}
        ),
        "role_disagreements": sum(r.get("role_disagrees", False) for r in records),
        "unknown_process_roles": sum(r["process_role"] is None for r in records),
        "records": records,
        "scope": (
            "Pinned 36-match feasibility sample; retrospective identity evidence, "
            "not operational lineup reconstruction"
        ),
        "provider_semantics": (
            "League-match xG remains separate from additive roster/shot xG; no sum constraint"
        ),
    }
