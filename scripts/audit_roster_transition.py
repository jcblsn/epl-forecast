"""Audit bounded departure exposure before admitting an offseason variance test."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from epl_forecast.artifacts import execution_provenance
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.research.roster_transition import captured_transfer_players, departure_exposure
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(args.manifest.read_text())
    data = frozen_dataset(args.data, args.manifest)
    try:
        fixtures = data.fixtures()
        appearances = data.rows("SELECT * FROM appearances")
        transfers = defaultdict(list)
        for row in data.rows("SELECT * FROM transfers"):
            transfers[row["player_id"]].append(row)
        captured = captured_transfer_players(data.manifests, data.rows("SELECT * FROM players"))
    finally:
        data.close()
    cohorts = {(r["competition_id"], r["season_id"]): r for r in frozen["readiness"]["cohorts"]}
    by_season = defaultdict(list)
    for fixture in fixtures:
        if fixture["stage"] == "regular":
            by_season[fixture["competition_id"], fixture["season_id"]].append(fixture)
    minutes = defaultdict(lambda: defaultdict(int))
    regular_finished = {
        f["match_id"] for f in fixtures if f["stage"] == "regular" and f["status"] == "finished"
    }
    for row in appearances:
        if row["minutes"] is not None and row["match_id"] in regular_finished:
            minutes[row["season_id"], row["team_id"]][row["player_id"]] += row["minutes"]
    collisions = {
        r["match_id"]
        for r in frozen["readiness"]["identity_contradictions"]["same_team_name_collisions"]
    }
    rows = []
    for (competition, season), games in sorted(by_season.items()):
        year = int(season[:4])
        if (
            not frozen["readiness"]["window"]["recent_player_start"]
            < year
            <= frozen["readiness"]["window"]["end"]
        ):
            continue
        previous = f"{year - 1}-{year}"
        cutoff = min(g["match_date"] for g in games)
        for team in sorted({g["home_team_id"] for g in games}):
            source_keys = [
                k
                for k, fs in by_season.items()
                if k[1] == previous
                and any(team in (g["home_team_id"], g["away_team_id"]) for g in fs)
            ]
            if len(source_keys) != 1:
                rows.append(
                    {
                        "team_id": team,
                        "season_id": season,
                        "eligible": False,
                        "reasons": ["no unique prior division in retained two-league window"],
                    }
                )
                continue
            source_key = source_keys[0]
            source = cohorts.get(source_key, {})
            source_games = by_season[source_key]
            team_games = {
                g["match_id"]
                for g in source_games
                if team in (g["home_team_id"], g["away_team_id"])
            }
            reasons = []
            if not source.get("complete_season"):
                reasons.append("incomplete prior season")
            if team_games - set(source.get("valid_matches", {}).get("starter_minutes", [])):
                reasons.append("incomplete prior starter exposure")
            if team_games & collisions:
                reasons.append("prior-season identity contradiction")
            exposure = minutes[previous, team]
            if not sum(exposure.values()):
                reasons.append("missing prior player minutes")
                feature = {}
            else:
                feature = departure_exposure(
                    team,
                    exposure,
                    transfers,
                    captured,
                    max(g["match_date"] for g in source_games),
                    cutoff,
                )
                if feature["unknown_minutes_share"] > 0:
                    reasons.append("unresolved departure exposure")
            rows.append(
                {
                    **feature,
                    "team_id": team,
                    "competition_id": competition,
                    "season_id": season,
                    "source_competition_id": source_key[0],
                    "eligible": not reasons,
                    "reasons": reasons,
                }
            )
    report = {
        "execution": execution_provenance(),
        "manifest_sha256": file_hash(args.manifest),
        "rows": rows,
        "eligible": sum(r["eligible"] for r in rows),
        "total": len(rows),
        "decision": "Eligibility measures retrospective recorded-departure exposure only. It does not establish complete squad composition, strict replay, or a useful variance predictor. Fit/test a pooled transition only on admitted cohorts and retain a constant-variance comparator.",
    }
    write_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("eligible", "total")}))


if __name__ == "__main__":
    main()
