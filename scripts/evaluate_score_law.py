"""Compare one shared Gamma match-intensity score law with the independent Poisson control."""

import argparse
import csv
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, write_csv
from epl_forecast.research.score_law import (
    BASELINES,
    chronological_score_law,
    distribution,
    event_calibration,
    summarize,
)
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baselines",
        type=Path,
        default=Path("docs/experiments/m8/chronological_predictions.csv.gz"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-scored", type=date.fromisoformat, default=date(2024, 8, 1))
    parser.add_argument("--minimum-training", type=int, default=200)
    args = parser.parse_args()
    new_run_directory(args.output)
    with gzip.open(args.baselines, "rt") as stream:
        rows = [row for row in csv.DictReader(stream) if row["model_id"] in BASELINES]
    errors = [
        abs(
            distribution(row).log_probability(int(row["home_goals"]), int(row["away_goals"]))
            - float(row["score_log_probability"])
        )
        for row in rows
    ]
    if max(errors) > 1e-8:
        raise ValueError("Saved state reconstruction changed the original score likelihood")
    print(f"State reconstruction max error {max(errors):.3g}", flush=True)
    config = {
        "baselines_sha256": file_hash(args.baselines),
        "first_scored": str(args.first_scored),
        "minimum_training": args.minimum_training,
        "control": "independent Poisson conditional on the same saved state",
        "candidate": "one shared Gamma match intensity, shape refit chronologically",
    }
    evaluation = {"predictions": [], "fits": [], "skipped": []}
    for model_id in BASELINES:
        subset = [row for row in rows if row["model_id"] == model_id]
        print(f"Scoring {model_id} on {len(subset)} saved fixtures", flush=True)
        block = chronological_score_law(subset, str(args.first_scored), args.minimum_training)
        evaluation["predictions"].extend(block["predictions"])
        evaluation["fits"].extend({"model_id": model_id, **fit} for fit in block["fits"])
        evaluation["skipped"].extend({"model_id": model_id, **row} for row in block["skipped"])
    predictions = evaluation["predictions"]
    write_csv(args.output / "predictions.csv", list(predictions[0]), predictions)

    def dispersion_summary(model_id):
        fits = [f for f in evaluation["fits"] if f["model_id"] == model_id]
        shapes = [f["dispersion"] for f in fits]
        return {
            "cutoffs": len(fits),
            "median": float(np.median(shapes)),
            "minimum": float(np.min(shapes)),
            "maximum": float(np.max(shapes)),
            "at_boundary": sum(f["at_boundary"] for f in fits),
        }

    summary = {
        "config": config,
        "state_reconstruction_max_error": max(errors),
        "dispersion": {model_id: dispersion_summary(model_id) for model_id in BASELINES},
        "comparisons": {model_id: summarize(predictions, model_id) for model_id in BASELINES},
        "events": event_calibration(rows, predictions),
        "fits": evaluation["fits"],
        "skipped": evaluation["skipped"],
    }
    write_json(args.output / "summary.json", summary)
    for model_id in BASELINES:
        block = summary["comparisons"][model_id]
        print(f"== {model_id} n={block['fixtures']}", flush=True)
        for metric, values in block["metrics"].items():
            print(
                f"   {metric:9s} poisson {values['poisson']:.5f}"
                f" gamma {values['shared_gamma']:.5f}"
                f" difference {values['difference']:+.5f}"
                f" [{values['interval'][0]:+.5f}, {values['interval'][1]:+.5f}]",
                flush=True,
            )
    print(json.dumps(summary["dispersion"], indent=2), flush=True)
    print(json.dumps(summary["events"], indent=2), flush=True)


if __name__ == "__main__":
    main()
