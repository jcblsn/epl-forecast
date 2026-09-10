"""Test an actual-minutes versus identity-preserving core-XI contrast on team xG residuals."""

import argparse
import csv
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory
from epl_forecast.cli import save_rows
from epl_forecast.research.portable_players import PortablePlayerLayer, portable_observation_rows
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.research.roster_bridge import BASELINES, prepare_cases
from epl_forecast.storage import file_hash, write_json


def fit_mapping(features, residuals, ridge=1.0):
    x = np.asarray(features, dtype=float)
    y = np.asarray(residuals, dtype=float)
    return np.linalg.solve(x.T @ x + ridge * np.eye(x.shape[1]), x.T @ y)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("runs/research-ready-v2-player-layer/manifest.json")
    )
    parser.add_argument(
        "--baselines",
        type=Path,
        default=Path("docs/experiments/m8/chronological_predictions.csv.gz"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-matches", type=int, default=8)
    parser.add_argument("--evaluation-start", type=date.fromisoformat, default=date(2024, 8, 1))
    args = parser.parse_args()
    new_run_directory(args.output)
    with gzip.open(args.baselines, "rt") as stream:
        baselines = [row for row in csv.DictReader(stream) if row["model_id"] in BASELINES]
    data = frozen_dataset(args.data, args.manifest)
    try:
        snapshot = json.loads(args.manifest.read_text())
        portable = PortablePlayerLayer(
            portable_observation_rows(data), snapshot["canonical_snapshot_sha256"]
        )
        appearances = data.rows(
            "SELECT * FROM appearances WHERE competition_id IN ('eng-premier-league','eng-championship') ORDER BY kickoff_time,player_id"
        )
        availability = data.rows("SELECT * FROM availability WHERE provider='api_football'")
        process = {row["match_id"]: row for row in data.process()}
        cases, excluded = prepare_cases(
            baselines,
            appearances,
            portable,
            availability,
            reference_matches=args.reference_matches,
            reference_strategy="core_xi",
            progress=lambda index, total, prepared: print(
                f"Prepared {index}/{total}; eligible {prepared}", flush=True
            ),
        )
    finally:
        data.close()
    observations = []
    for case in cases:
        target = process.get(case["match_id"])
        if target is None:
            continue
        for model in BASELINES:
            baseline = case["baselines"][model]
            for side in ("home", "away"):
                expected = float(baseline[f"expected_{side}_goals"])
                xg = float(target[f"{side}_xg"])
                observations.append(
                    {
                        "model_id": model,
                        "match_id": case["match_id"],
                        "match_date": str(case["match_date"]),
                        "season_id": baseline["season_id"],
                        "side": side,
                        "xg_residual": float(np.log1p(xg) - np.log1p(expected)),
                        "shooting_contrast": float(case[side]["mean"][0]),
                        "creation_contrast": float(case[side]["mean"][1]),
                        "changed_match_equivalents": case[side]["changed_match_equivalents"],
                    }
                )
    summaries = []
    for model in BASELINES:
        model_rows = [row for row in observations if row["model_id"] == model]
        training = [
            row
            for row in model_rows
            if date.fromisoformat(row["match_date"]) < args.evaluation_start
        ]
        evaluation = [
            row
            for row in model_rows
            if date.fromisoformat(row["match_date"]) >= args.evaluation_start
        ]
        train_x = [[row["shooting_contrast"], row["creation_contrast"]] for row in training]
        train_y = [row["xg_residual"] for row in training]
        beta = fit_mapping(train_x, train_y)
        test_x = np.array(
            [[row["shooting_contrast"], row["creation_contrast"]] for row in evaluation]
        )
        test_y = np.array([row["xg_residual"] for row in evaluation])
        prediction = test_x @ beta
        baseline_mse = float(np.mean(test_y**2))
        candidate_mse = float(np.mean((test_y - prediction) ** 2))
        summaries.append(
            {
                "model_id": model,
                "training_team_matches": len(training),
                "evaluation_team_matches": len(evaluation),
                "shooting_coefficient": float(beta[0]),
                "creation_coefficient": float(beta[1]),
                "baseline_xg_residual_mse": baseline_mse,
                "core_xi_delta_xg_residual_mse": candidate_mse,
                "mse_difference": candidate_mse - baseline_mse,
                "fraction_mse_reduction": (baseline_mse - candidate_mse) / baseline_mse,
                "residual_prediction_correlation": float(np.corrcoef(test_y, prediction)[0, 1]),
                "mean_changed_match_equivalents": float(
                    np.mean([row["changed_match_equivalents"] for row in evaluation])
                ),
            }
        )
    save_rows(args.output / "summary.csv", summaries)
    write_json(
        args.output / "manifest.json",
        {
            "mode": "discovery",
            "oracle_input": "actual target identities and minutes",
            "reference": f"top 11 player identities by minutes over {args.reference_matches} prior eligible matches, each assigned 90 minutes",
            "target": "log1p actual team xG minus log1p structural expected goals",
            "evaluation_start": str(args.evaluation_start),
            "prepared_fixtures": len(cases),
            "process_matched_fixtures": len({row["match_id"] for row in observations}),
            "excluded_fixtures": len(excluded),
            "baselines_sha256": file_hash(args.baselines),
            "research_manifest_sha256": file_hash(args.manifest),
            "interpretation": "Retrospective known-minutes ceiling diagnostic; not a deployable lineup forecast.",
        },
    )


if __name__ == "__main__":
    main()
