"""Reproducible, resumable historical season scoring for retained model specifications."""

import argparse
import json
from pathlib import Path

from epl_forecast.artifacts import execution_provenance
from epl_forecast.cli import fitted_model, load_config, save_rows
from epl_forecast.datasets import Dataset
from epl_forecast.sanctions import REGISTRIES, load_registry
from epl_forecast.season_evaluation import (
    final_cutoff,
    promotion_season_truth,
    score_forecast,
    season_origins,
    season_teams,
    season_truth,
    summarize,
)
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, write_json

SPECS = {
    "M2": ("configs/dynamic.toml", "M2-attack-defense-v1"),
    "M4": ("configs/dynamic.toml", "M4-dynamic-hierarchical-v1"),
    "M5": ("configs/quality_tilt.toml", "M5-quality-tilt-v1"),
    "M7": ("configs/xg_quality_tilt.toml", "M7-xg-v1"),
}


def competition_config(name, competition):
    config_path, model_id = SPECS[name]
    config = load_config(Path(config_path))
    config["competition_id"] = competition
    for spec in config["models"]:
        spec.setdefault("parameters", {})["competition_id"] = competition
    return config, model_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--simulations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2015, 2026)))
    parser.add_argument("--models", nargs="+", choices=SPECS, default=list(SPECS))
    parser.add_argument(
        "--competition",
        choices=("eng-premier-league", "eng-championship"),
        default="eng-premier-league",
    )
    args = parser.parse_args()
    data = Dataset(args.data)
    try:
        matches = data.matches()
        manifest = data.provenance()
        sanctions = load_registry(data)
    finally:
        data.close()
    configs = {name: competition_config(name, args.competition)[0] for name in args.models}
    metadata = {
        "execution": execution_provenance(),
        "simulations": args.simulations,
        "seed": args.seed,
        "seasons": args.seasons,
        "models": args.models,
        "data_manifest": manifest,
        "competition_id": args.competition,
        "configs": configs,
        "code_hashes": {str(p): file_hash(p) for p in sorted(Path("src").rglob("*.py"))},
        "runner_hash": file_hash(Path(__file__)),
        "reviewed_adjustment_hashes": {
            name: file_hash(Path("src/epl_forecast/data") / name) for name in REGISTRIES
        },
        "sanction_audit": [
            row for row in sanctions.audit() if row["competition_id"] == args.competition
        ],
        "truth_definition": (
            "Final table from fixed results plus every sanction the retained standings show "
            "in force at the end of the season; seasons without a usable standings snapshot "
            "fall back to results alone and are named in unsanctioned_seasons"
        ),
        "origin_definition": (
            "Start of first match date; next day after 6/12/19/30 nominal rounds, whole days"
        ),
    }
    metadata_path = args.output / "manifest.json"
    if metadata_path.exists() and json.loads(metadata_path.read_text()) != metadata:
        raise ValueError("Resume manifest differs; use a new output directory")
    write_json(metadata_path, metadata)
    league = [m for m in matches if m.fixture.competition_id == args.competition]
    rows, unsanctioned = [], []
    for year in args.seasons:
        season = f"{year}-{year + 1}"
        season_matches = [m for m in league if m.fixture.season_id == season]
        origins = season_origins(season_matches)
        teams = sorted(
            {t for m in season_matches for t in (m.fixture.home_team_id, m.fixture.away_team_id)}
        )
        previous = season_teams(matches, args.competition, f"{year - 1}-{year}")
        expected = 20 if args.competition == "eng-premier-league" else 24
        if len(previous) != expected:
            raise ValueError("Missing previous season for promotion labels")
        cutoff = final_cutoff(season_matches)
        final = sanctions.final_adjustments(args.competition, season, cutoff)
        if not sanctions.derivation(args.competition, season)["sanctioned_table_available"]:
            unsanctioned.append(season)
        if args.competition == "eng-championship":
            truth = promotion_season_truth(matches, season, season_matches, teams, args.seed, final)
        else:
            truth = season_truth(season_matches, teams, args.seed, final)
        previous_pl = season_teams(matches, "eng-premier-league", f"{year - 1}-{year}")
        entry_cohorts = {
            team: (
                "incumbent"
                if team in previous
                else "relegated_from_pl"
                if args.competition == "eng-championship" and team in previous_pl
                else "promoted_from_lower"
            )
            for team in teams
        }
        for origin_index, (origin, as_of) in enumerate(origins.items()):
            seed = args.seed + year * 10 + origin_index
            played = [m for m in season_matches if m.available_on <= as_of]
            remaining = [m.fixture for m in season_matches if m.available_on > as_of]
            for name in args.models:
                path = args.output / "forecasts" / f"{season}-{origin}-{name}.json"
                if path.exists():
                    forecast = json.loads(path.read_text())
                else:
                    print(f"Fitting {season} {origin} {name} ({len(played)} played)", flush=True)
                    config = metadata["configs"][name]
                    model, _, _ = fitted_model(matches, config, SPECS[name][1], as_of)
                    forecast = simulate_season(
                        model,
                        played,
                        remaining,
                        teams,
                        as_of,
                        args.simulations,
                        seed,
                        sanctions.known_adjustments(args.competition, season, as_of),
                    )
                    write_json(path, forecast)
                rows.extend(
                    {
                        "model_id": name,
                        "season_id": season,
                        "origin": origin,
                        "as_of": str(as_of),
                        "played_matches": len(played),
                        **row,
                    }
                    for row in score_forecast(
                        forecast,
                        truth,
                        {team for team, cohort in entry_cohorts.items() if cohort != "incumbent"},
                        seed,
                        entry_cohorts,
                    )
                )
                save_rows(args.output / "club_seasons.csv", rows)
    write_json(
        args.output / "sanctions.json",
        {
            "competition_id": args.competition,
            "unsanctioned_seasons": unsanctioned,
            "seasons": [
                sanctions.derivation(args.competition, f"{year}-{year + 1}")
                for year in args.seasons
            ],
        },
    )
    summary, calibration = summarize(rows)
    save_rows(args.output / "summary.csv", summary)
    save_rows(args.output / "calibration.csv", calibration)
    per_season = []
    for season in sorted({r["season_id"] for r in rows}):
        scores, _ = summarize([r for r in rows if r["season_id"] == season])
        per_season.extend({"season_id": season, **r} for r in scores)
    save_rows(args.output / "by_season.csv", per_season)
    subgroup_rows = []
    for cohort in sorted({r["entry_cohort"] for r in rows}):
        cohort_summary, _ = summarize([r for r in rows if r["entry_cohort"] == cohort])
        subgroup_rows.extend({"entry_cohort": cohort, **row} for row in cohort_summary)
    save_rows(args.output / "subgroups.csv", subgroup_rows)
    print(args.output / "summary.csv", flush=True)


if __name__ == "__main__":
    main()
