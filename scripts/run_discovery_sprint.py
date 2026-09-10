"""Run cheap low-score, market-disagreement and flexible-scouting diagnostics."""

import argparse
import csv
import gzip
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory
from epl_forecast.cli import save_rows
from epl_forecast.evaluation import individual_metrics, metrics
from epl_forecast.research.discovery_sprint import (
    fit_low_score_rho,
    fit_multinomial,
    market_disagreement_features,
    predict_multinomial,
    score_low_score,
    scouting_features,
)
from epl_forecast.schema import OUTCOMES
from epl_forecast.storage import file_hash, write_json

STRUCTURAL = ["M2-attack-defense-v1", "M5-quality-tilt-poisson", "M7-xg-v1"]
MARKET = "market:market_average_preclosing"


def read_rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def index(rows, models):
    result = {model: {} for model in models}
    for row in rows:
        if row["model_id"] not in result:
            continue
        if row["match_id"] in result[row["model_id"]]:
            raise ValueError("Duplicate discovery prediction")
        result[row["model_id"]][row["match_id"]] = row
    if any(not group for group in result.values()):
        raise ValueError("Missing discovery model")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--markets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirmation-start", type=date.fromisoformat, default=date(2025, 7, 1))
    args = parser.parse_args()
    new_run_directory(args.output)
    structural = index(read_rows(args.predictions), STRUCTURAL)
    market = index(read_rows(args.markets), [MARKET])[MARKET]
    common = sorted(set.intersection(*(set(group) for group in structural.values()), set(market)))
    if not common:
        raise ValueError("No common discovery fixtures")

    low_score_rows = []
    for model in (STRUCTURAL[0], STRUCTURAL[2]):
        rows = [structural[model][key] for key in common]
        training = [
            r for r in rows if date.fromisoformat(r["match_date"]) < args.confirmation_start
        ]
        evaluation = [
            r for r in rows if date.fromisoformat(r["match_date"]) >= args.confirmation_start
        ]
        chronological = fit_low_score_rho(training)
        ceiling = fit_low_score_rho(evaluation)
        baseline = score_low_score(evaluation, 0)
        confirmed = score_low_score(evaluation, chronological["rho"])
        attainable = score_low_score(evaluation, ceiling["rho"])
        low_score_rows.append(
            {
                "model_id": model,
                "training_matches": len(training),
                "evaluation_matches": len(evaluation),
                "chronological_rho": chronological["rho"],
                "oracle_evaluation_rho": ceiling["rho"],
                "baseline_log_loss": baseline["log_loss"],
                "chronological_delta_log_loss": confirmed["log_loss"] - baseline["log_loss"],
                "oracle_delta_log_loss": attainable["log_loss"] - baseline["log_loss"],
                "baseline_score_nll": baseline["score_nll"],
                "chronological_delta_score_nll": confirmed["score_nll"] - baseline["score_nll"],
                "oracle_delta_score_nll": attainable["score_nll"] - baseline["score_nll"],
            }
        )
    save_rows(args.output / "low_score.csv", low_score_rows)

    disagreement = []
    for key in common:
        row = structural[STRUCTURAL[2]][key]
        disagreement.append(
            {
                "match_id": key,
                "season_id": row["season_id"],
                **market_disagreement_features(row, market[key]),
            }
        )
    targets = [
        "market_minus_structural_home",
        "market_minus_structural_draw",
        "market_minus_structural_away",
    ]
    predictors = [
        "expected_total_goals",
        "expected_goal_difference",
        "quality_gap",
        "tilt_sum",
        "rate_uncertainty",
        "structural_entropy",
    ]
    correlations = []
    for target in targets:
        for predictor in predictors:
            correlations.append(
                {
                    "target": target,
                    "predictor": predictor,
                    "correlation": float(
                        np.corrcoef(
                            [row[target] for row in disagreement],
                            [row[predictor] for row in disagreement],
                        )[0, 1]
                    ),
                    "matches": len(disagreement),
                }
            )
    save_rows(args.output / "market_disagreement.csv", correlations)
    explanatory_models = []
    train_disagreement = [
        row for row in disagreement if int(row["season_id"][:4]) < args.confirmation_start.year
    ]
    test_disagreement = [
        row for row in disagreement if int(row["season_id"][:4]) >= args.confirmation_start.year
    ]
    train_x = np.array([[row[key] for key in predictors] for row in train_disagreement])
    test_x = np.array([[row[key] for key in predictors] for row in test_disagreement])
    mean, scale = train_x.mean(axis=0), train_x.std(axis=0)
    scale[scale < 1e-8] = 1
    train_design = np.column_stack([np.ones(len(train_x)), (train_x - mean) / scale])
    test_design = np.column_stack([np.ones(len(test_x)), (test_x - mean) / scale])
    penalty = np.diag([0, *([1.0] * len(predictors))])
    for target in targets:
        train_y = np.array([row[target] for row in train_disagreement])
        test_y = np.array([row[target] for row in test_disagreement])
        beta = np.linalg.solve(train_design.T @ train_design + penalty, train_design.T @ train_y)
        prediction = test_design @ beta
        baseline_error = np.sum((test_y - train_y.mean()) ** 2)
        r_squared = 1 - np.sum((test_y - prediction) ** 2) / baseline_error
        for predictor, coefficient in zip(("intercept", *predictors), beta, strict=True):
            explanatory_models.append(
                {
                    "target": target,
                    "predictor": predictor,
                    "standardized_coefficient": float(coefficient),
                    "chronological_test_r_squared": float(r_squared),
                    "training_matches": len(train_disagreement),
                    "evaluation_matches": len(test_disagreement),
                }
            )
    save_rows(args.output / "market_disagreement_models.csv", explanatory_models)

    predictions = []
    for season in ("2024-2025", "2025-2026"):
        target_ids = [
            key for key in common if structural[STRUCTURAL[0]][key]["season_id"] == season
        ]
        first_date = min(
            date.fromisoformat(structural[STRUCTURAL[0]][key]["match_date"]) for key in target_ids
        )
        train_ids = [
            key
            for key in common
            if date.fromisoformat(structural[STRUCTURAL[0]][key]["match_date"]) < first_date
        ]
        train_features = scouting_features(structural, train_ids)
        train_outcomes = np.array(
            [OUTCOMES.index(structural[STRUCTURAL[0]][key]["outcome"]) for key in train_ids]
        )
        fit = fit_multinomial(train_features, train_outcomes)
        probabilities = predict_multinomial(fit, scouting_features(structural, target_ids))
        for key, probability in zip(target_ids, probabilities, strict=True):
            source = structural[STRUCTURAL[0]][key]
            predictions.append(
                {
                    "model_id": "discovery:regularized-multinomial-scout",
                    "match_id": key,
                    "season_id": season,
                    "match_date": source["match_date"],
                    "outcome": source["outcome"],
                    "p_home": float(probability[0]),
                    "p_draw": float(probability[1]),
                    "p_away": float(probability[2]),
                    "score_log_probability": None,
                    "training_matches": len(train_ids),
                }
            )
    evaluation_ids = {row["match_id"] for row in predictions}
    scouting_summary = [
        {"model_id": model, **metrics([group[key] for key in sorted(evaluation_ids)])[0]}
        for model, group in structural.items()
    ]
    scouting_summary.append({"model_id": predictions[0]["model_id"], **metrics(predictions)[0]})
    market_rows = [market[key] for key in sorted(evaluation_ids)]
    scouting_summary.append({"model_id": MARKET, **metrics(market_rows)[0]})
    save_rows(args.output / "scouting_summary.csv", scouting_summary)
    by_season = []
    for season in ("2024-2025", "2025-2026"):
        selected = [r for r in predictions if r["season_id"] == season]
        candidate = metrics(selected)[0]
        candidate["model_id"] = predictions[0]["model_id"]
        candidate["season_id"] = season
        by_season.append(candidate)
    save_rows(args.output / "scouting_by_season.csv", by_season)
    y = np.array([OUTCOMES.index(r["outcome"]) for r in predictions])
    p = np.array([[r[f"p_{side}"] for side in ("home", "draw", "away")] for r in predictions])
    losses, _ = individual_metrics(p, y)
    write_json(
        args.output / "summary.json",
        {
            "mode": "discovery",
            "matched_fixtures": len(common),
            "scouting_evaluation_matches": len(predictions),
            "scouting_mean_log_loss": float(losses.mean()),
            "low_score": low_score_rows,
            "largest_market_disagreement_correlations": sorted(
                correlations, key=lambda row: abs(row["correlation"]), reverse=True
            )[:8],
            "market_disagreement_chronological_r_squared": {
                target: next(
                    row["chronological_test_r_squared"]
                    for row in explanatory_models
                    if row["target"] == target
                )
                for target in targets
            },
            "predictions_sha256": file_hash(args.predictions),
            "markets_sha256": file_hash(args.markets),
            "interpretation": "Retrospective discovery diagnostics; candidates require separate confirmation before deployment.",
        },
    )


if __name__ == "__main__":
    main()
