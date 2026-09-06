import argparse
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

from epl_forecast.data.normalize import write_csv
from epl_forecast.evaluation import metrics
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    groups = defaultdict(list)
    inputs = {}
    for directory in args.evaluations:
        path = directory / "predictions.csv"
        inputs[str(path)] = file_hash(path)
        for row in csv.DictReader(path.open()):
            groups[row["model_id"]].append(row)
    summary, seasons, slices, states = [], [], [], []
    for model, rows in groups.items():
        if len({r["match_id"] for r in rows}) != len(rows):
            raise ValueError("Overlapping evaluation matches")
        summary.append({"model_id": model, **metrics(rows)[0]})
        for season in sorted({r["season_id"] for r in rows}):
            seasons.append(
                {
                    "model_id": model,
                    "season_id": season,
                    **metrics([r for r in rows if r["season_id"] == season])[0],
                }
            )
        for label, subset in (
            ("August-September", [r for r in rows if r["match_date"][5:7] in {"08", "09"}]),
            ("Other months", [r for r in rows if r["match_date"][5:7] not in {"08", "09"}]),
        ):
            slices.append({"model_id": model, "slice": label, **metrics(subset)[0]})
        if not rows[0].get("home_quality"):
            continue
        for key in ("quality", "tilt", "quality_sd", "tilt_sd"):
            values = [float(r[f"{side}_{key}"]) for r in rows for side in ("home", "away")]
            states.append(
                {
                    "model_id": model,
                    "state": key,
                    "mean": float(np.mean(values)),
                    "q05": float(np.quantile(values, 0.05)),
                    "q95": float(np.quantile(values, 0.95)),
                }
            )
    tails = []
    path = args.scores / "predictions.csv"
    inputs[str(path)] = file_hash(path)
    score_groups = defaultdict(list)
    for row in csv.DictReader(path.open()):
        score_groups[row["model_id"]].append(row)
    for model, rows in score_groups.items():
        goals = np.array([[int(r["home_goals"]), int(r["away_goals"])] for r in rows])
        for key, observed in (
            ("p_draw", goals[:, 0] == goals[:, 1]),
            ("p_scoreless", goals.sum(axis=1) == 0),
            ("p_total_goals_ge6", goals.sum(axis=1) >= 6),
            ("p_both_score", np.all(goals > 0, axis=1)),
        ):
            predicted = np.array([float(r[key]) for r in rows])
            tails.append(
                {
                    "model_id": model,
                    "event": key,
                    "matches": len(rows),
                    "predicted": float(predicted.mean()),
                    "observed": float(observed.mean()),
                    "binary_brier": float(np.mean((predicted - observed) ** 2)),
                }
            )
    for name, rows in (
        ("overall", summary),
        ("by_season", seasons),
        ("slices", slices),
        ("states", states),
        ("score_events", tails),
    ):
        write_csv(args.output / f"{name}.csv", list(rows[0]), rows)
    write_json(args.output / "inputs.json", inputs)
    print(f"Wrote diagnostics to {args.output}")


if __name__ == "__main__":
    main()
