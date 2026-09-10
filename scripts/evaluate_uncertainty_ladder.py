"""Matched season uncertainty attribution from immutable canonical inputs."""

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.cli import save_rows
from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.quality_tilt import BayesianQualityTilt
from epl_forecast.models.xg_quality_tilt import (
    XG_DYNAMICS,
    BayesianXGQualityTilt,
    XGQualityTiltFilter,
)
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.research.uncertainty_ladder import M2SeasonDependence, MatchedStateForecast
from epl_forecast.sanctions import load_registry
from epl_forecast.season_evaluation import final_cutoff, score_forecast, season_origins, summarize
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json

DEPENDENCE = (0.0, 0.1, 0.25, 0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2015, 2026)))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260909)
    parser.add_argument("--skip-rich-benchmarks", action="store_true")
    args = parser.parse_args()
    if args.seasons != sorted(set(args.seasons)):
        raise ValueError("Seasons must be unique and chronological")
    frozen = json.loads(args.manifest.read_text())
    eligible = frozen["readiness"]["eligible_cohorts"]["matched_uncertainty_ladder"]
    if any(["eng-premier-league", f"{year}-{year + 1}"] not in eligible for year in args.seasons):
        raise ValueError("Season not admitted by research manifest")
    metadata = {
        "execution": execution_provenance(),
        "manifest_sha256": file_hash(args.manifest),
        "seasons": args.seasons,
        "simulations": args.simulations,
        "seed": args.seed,
        "skip_rich_benchmarks": args.skip_rich_benchmarks,
        "dynamics": XG_DYNAMICS,
        "matched_xg_probability": 0.2,
        "dependence_grid": DEPENDENCE,
        "calibration": "At each origin choose M2 dependence by mean points CRPS across earlier completed seasons at that same origin; first season uses zero.",
        "scope": "Historical development evidence. Match scores are origin-conditioned forecasts of all remaining matches, not daily refits. Next-day outcome availability assumed.",
        "promoted_switch": "Condition the joint current posterior on promoted-team coordinates equal to their posterior means; preserve all means. Future innovations remain enabled. This isolates current promoted-state uncertainty, not the effect of retraining with a different entry prior.",
    }
    write_immutable(args.output / "manifest.json", json_bytes(metadata))
    data = frozen_dataset(args.data, args.manifest)
    try:
        matches, observations = data.matches(), data.process()
        sanctions = load_registry(data)
    finally:
        data.close()
    parents = {
        "goals": CenteredQualityTiltFilter(**XG_DYNAMICS),
        "xg": XGQualityTiltFilter(observations, 0.2, **XG_DYNAMICS),
    }
    if not args.skip_rich_benchmarks:
        parents.update(
            M4=DynamicAttackDefense(),
            M5=BayesianQualityTilt(),
            M7=BayesianXGQualityTilt(observations),
        )
    premier = [m for m in matches if m.fixture.competition_id == "eng-premier-league"]
    season_rows, match_rows, calibration_rows = [], [], []
    for year in args.seasons:
        season = f"{year}-{year + 1}"
        games = [m for m in premier if m.fixture.season_id == season]
        teams = sorted({m.fixture.home_team_id for m in games})
        previous = {
            m.fixture.home_team_id for m in premier if m.fixture.season_id == f"{year - 1}-{year}"
        }
        if len(previous) != 20:
            raise ValueError("Missing previous season for promotion labels")
        promoted = set(teams) - previous
        end = final_cutoff(games)
        truth_model = AttackDefensePoisson()
        truth_model.as_of = end
        truth = simulate_season(
            truth_model,
            games,
            [],
            teams,
            end,
            1,
            args.seed,
            sanctions.final_adjustments("eng-premier-league", season, end),
        )
        for origin_index, (origin, cutoff) in enumerate(season_origins(games).items()):
            print(f"Fitting {season} {origin}", flush=True)
            training = [m for m in matches if m.available_on <= cutoff]
            for parent in parents.values():
                parent.fit(training, cutoff)
            m2 = AttackDefensePoisson(half_life_days=365, ridge=5).fit(
                [
                    m
                    for m in premier
                    if cutoff - timedelta(days=1095) <= m.fixture.match_date
                    and m.available_on <= cutoff
                ],
                cutoff,
            )
            goals, xg = parents["goals"], parents["xg"]
            variants = {
                "fixed": MatchedStateForecast(goals, teams, season, posterior=False),
                "posterior": MatchedStateForecast(goals, teams, season),
                "drift": MatchedStateForecast(
                    goals, teams, season, evolution=True, innovations=False
                ),
                "evolution": MatchedStateForecast(goals, teams, season, evolution=True),
                "conditional_promoted": MatchedStateForecast(
                    goals, teams, season, evolution=True, fixed_teams=promoted
                ),
                "xg": MatchedStateForecast(xg, teams, season, evolution=True),
                "gamma_scores": MatchedStateForecast(
                    goals, teams, season, evolution=True, dispersion=20
                ),
                "M2": m2,
            }
            variants.update({k: v for k, v in parents.items() if k in {"M4", "M5", "M7"}})
            variants.update(
                {
                    f"M2_dependence_{weight}": M2SeasonDependence(m2, teams, weight)
                    for weight in DEPENDENCE
                }
            )
            history = [r for r in season_rows if r["season_id"] < season and r["origin"] == origin]
            losses = {
                weight: [
                    r["points_crps"] for r in history if r["model_id"] == f"M2_dependence_{weight}"
                ]
                for weight in DEPENDENCE
            }
            selected = min(DEPENDENCE, key=lambda w: np.mean(losses[w])) if history else 0.0
            calibration_rows.append(
                {
                    "season_id": season,
                    "origin": origin,
                    "selected_dependence": selected,
                    "training_seasons": sorted({r["season_id"] for r in history}),
                    "candidate_crps": {
                        str(w): float(np.mean(v)) if v else None for w, v in losses.items()
                    },
                }
            )
            played = [m for m in games if m.available_on <= cutoff]
            remaining = [m for m in games if m.available_on > cutoff]
            cell_results = {}
            for name, model in variants.items():
                destination = args.output / "cells" / f"{season}-{origin}-{name}.json"
                if destination.exists():
                    cell = json.loads(destination.read_text())
                else:
                    print(f"Simulating {season} {origin} {name}", flush=True)
                    seed = args.seed + year * 10 + origin_index
                    forecast = simulate_season(
                        model,
                        played,
                        [m.fixture for m in remaining],
                        teams,
                        cutoff,
                        args.simulations,
                        seed,
                        sanctions.known_adjustments("eng-premier-league", season, cutoff),
                    )
                    forecast["uncertainty_attribution_variant"] = name
                    base = {
                        "model_id": name,
                        "season_id": season,
                        "origin": origin,
                        "as_of": str(cutoff),
                    }
                    scores = [
                        {**base, **r} for r in score_forecast(forecast, truth, promoted, seed)
                    ]
                    predictions = []
                    for match in remaining:
                        prediction = model.predict_match(match.fixture)
                        outcome = (
                            0
                            if match.home_goals > match.away_goals
                            else 1
                            if match.home_goals == match.away_goals
                            else 2
                        )
                        predictions.append(
                            {
                                **base,
                                "match_id": match.fixture.match_id,
                                "match_date": str(match.fixture.match_date),
                                "home_team_id": match.fixture.home_team_id,
                                "away_team_id": match.fixture.away_team_id,
                                "log_loss": -float(np.log(prediction.probabilities[outcome])),
                                "score_nll": -prediction.scores.log_probability(
                                    match.home_goals, match.away_goals
                                ),
                                "probabilities": list(prediction.probabilities),
                            }
                        )
                    cell = {
                        "forecast": forecast,
                        "season_scores": scores,
                        "match_scores": predictions,
                        "fit_diagnostics": getattr(model, "fit_diagnostics", None),
                    }
                    write_immutable(destination, json_bytes(cell))
                season_rows.extend(cell["season_scores"])
                match_rows.extend(cell["match_scores"])
                cell_results[name] = cell
            selected_cell = cell_results[f"M2_dependence_{selected}"]
            season_rows.extend(
                {**r, "model_id": "M2_calibrated"} for r in selected_cell["season_scores"]
            )
            match_rows.extend(
                {**r, "model_id": "M2_calibrated"} for r in selected_cell["match_scores"]
            )
            save_rows(args.output / "club_seasons.csv", season_rows)
            write_json(args.output / "match_scores.json", match_rows)
            write_json(args.output / "calibration_selection.json", calibration_rows)
            summary, calibration = summarize(season_rows)
            save_rows(args.output / "summary.csv", summary)
            save_rows(args.output / "calibration.csv", calibration)
    write_json(
        args.output / "completion.json",
        {
            "completed_seasons": args.seasons,
            "season_rows": len(season_rows),
            "match_rows": len(match_rows),
        },
    )


if __name__ == "__main__":
    main()
