"""Compact a season-scoring run into a committable, rescorable marginal archive."""

import argparse
import gzip
import json
from pathlib import Path

from epl_forecast.data.rules import historical_adjustments
from epl_forecast.datasets import Dataset
from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.season_evaluation import (
    championship_season_truth,
    final_cutoff,
    season_teams,
)
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, write_json

CHAMPIONSHIP = "eng-championship"
KEEP = (
    "competition_id",
    "season_id",
    "as_of",
    "simulations",
    "seed",
    "played_matches",
    "remaining_matches",
    "playoff_model",
)


def marginal(forecast):
    """Everything the scorer reads, without the per-fixture frequencies."""
    return {key: forecast[key] for key in KEEP if key in forecast} | {
        "teams": [
            {key: value for key, value in team.items() if key != "goal_difference_distribution"}
            for team in forecast["teams"]
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    manifest = json.loads((args.evaluation / "manifest.json").read_text())
    competition = manifest["competition_id"]
    data = Dataset(args.data)
    try:
        matches = data.matches()
    finally:
        data.close()
    league = [m for m in matches if m.fixture.competition_id == competition]
    forecasts, truth, promoted, cohorts = [], {}, {}, {}
    for path in sorted((args.evaluation / "forecasts").glob("*.json")):
        season, origin, model = path.stem.rsplit("-", 2)
        forecast = json.loads(path.read_text())
        forecasts.append({"model_id": model, "origin": origin, "forecast": marginal(forecast)})
        if season in truth:
            continue
        season_matches = [m for m in league if m.fixture.season_id == season]
        teams = sorted({m.fixture.home_team_id for m in season_matches})
        year = int(season[:4])
        previous = season_teams(matches, competition, f"{year - 1}-{year}")
        previous_pl = season_teams(matches, "eng-premier-league", f"{year - 1}-{year}")
        if competition == CHAMPIONSHIP:
            truth[season] = championship_season_truth(
                matches, season, season_matches, teams, manifest["seed"]
            )
        else:
            cutoff = final_cutoff(season_matches)
            model_at_end = AttackDefensePoisson()
            model_at_end.as_of = cutoff
            truth[season] = simulate_season(
                model_at_end,
                season_matches,
                [],
                teams,
                cutoff,
                1,
                manifest["seed"],
                historical_adjustments(season, cutoff),
            )
        cohorts[season] = {
            team: (
                "incumbent"
                if team in previous
                else "relegated_from_pl"
                if competition == CHAMPIONSHIP and team in previous_pl
                else "promoted_from_lower"
            )
            for team in teams
        }
        promoted[season] = sorted(t for t, c in cohorts[season].items() if c != "incumbent")
    archive = {
        "schema_version": 1,
        "competition_id": competition,
        "source_manifest_sha256": file_hash(args.evaluation / "manifest.json"),
        "forecasts": forecasts,
        "truth": truth,
        "promoted": promoted,
        "entry_cohorts": cohorts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt") as stream:
        json.dump(archive, stream, sort_keys=True)
    write_json(
        args.output.with_suffix(".index.json"),
        {
            "archive_sha256": file_hash(args.output),
            "forecast_cells": len(forecasts),
            "seasons": sorted(truth),
            "competition_id": competition,
        },
    )
    print(args.output)


if __name__ == "__main__":
    main()
