"""Difference two season-scoring runs, club-season by club-season.

A correction to truth or to the simulator moves every score at once, so the useful
question is not whether the numbers changed but whether the comparisons they support
changed: which model wins each metric at each origin, and by how much relative to the
size of the change. Rows are matched on model, origin, season and club, and a run
that does not cover the same club-seasons is rejected rather than aligned.
"""

import argparse
import csv
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance, write_csv
from epl_forecast.storage import write_json

METRICS = (
    "rank_rps",
    "points_crps",
    "points_error",
    "rank_error",
    "coverage_90",
    "rank_coverage_90",
    "automatic_promotion_brier",
    "playoff_qualification_brier",
    "promotion_brier",
    "relegation_brier",
    "title_brier",
)
SCORES = tuple(m for m in METRICS if m.endswith(("_rps", "_crps", "_brier")))
ORIGINS = ("preseason", "MW6", "MW12", "MW19", "MW30")


def read_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def key_of(row):
    return row["model_id"], row["origin"], row["season_id"], row["team_id"]


def numeric(row, metric):
    value = row.get(metric)
    return float(value) if value not in (None, "") else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--revised", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = {key_of(r): r for r in read_rows(args.baseline / "club_seasons.csv")}
    revised = {key_of(r): r for r in read_rows(args.revised / "club_seasons.csv")}
    if set(baseline) != set(revised):
        raise ValueError("Runs must cover the same model, origin, season and club rows")

    rows = []
    for origin in ORIGINS:
        models = sorted({key[0] for key in baseline if key[1] == origin})
        for model in models:
            selected = [key for key in baseline if key[0] == model and key[1] == origin]
            for metric in METRICS:
                left = np.array([numeric(baseline[key], metric) for key in selected], dtype=float)
                right = np.array([numeric(revised[key], metric) for key in selected], dtype=float)
                if np.isnan(left).any() or np.isnan(right).any():
                    continue
                rows.append(
                    {
                        "model_id": model,
                        "origin": origin,
                        "metric": metric,
                        "club_seasons": len(selected),
                        "baseline": float(left.mean()),
                        "revised": float(right.mean()),
                        "change": float(right.mean() - left.mean()),
                        "max_absolute_club_change": float(np.abs(right - left).max()),
                        "clubs_changed": int(np.count_nonzero(right != left)),
                    }
                )

    # Only proper scores decide a model comparison. Bias and coverage are diagnostics:
    # a signed bias closest to zero is not a win, and coverage is judged against
    # nominal rather than maximized, so neither has a leader to preserve.
    verdicts = []
    for origin in ORIGINS:
        for metric in SCORES:
            selected = [r for r in rows if r["origin"] == origin and r["metric"] == metric]
            if len(selected) < 2:
                continue
            baseline_winner = min(selected, key=lambda r: r["baseline"])["model_id"]
            revised_winner = min(selected, key=lambda r: r["revised"])["model_id"]
            verdicts.append(
                {
                    "origin": origin,
                    "metric": metric,
                    "baseline_leader": baseline_winner,
                    "revised_leader": revised_winner,
                    "leader_unchanged": baseline_winner == revised_winner,
                    "baseline_gap": abs(selected[0]["baseline"] - selected[1]["baseline"]),
                    "revised_gap": abs(selected[0]["revised"] - selected[1]["revised"]),
                }
            )

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "metric_changes.csv", list(rows[0]), rows)
    write_csv(args.output / "leader_changes.csv", list(verdicts[0]), verdicts)
    write_json(
        args.output / "comparison.json",
        {
            "execution": execution_provenance(),
            "baseline": str(args.baseline),
            "revised": str(args.revised),
            "club_season_rows": len(baseline),
            "leaders_unchanged": sum(v["leader_unchanged"] for v in verdicts),
            "leaders_compared": len(verdicts),
            "reversed_comparisons": [v for v in verdicts if not v["leader_unchanged"]],
        },
    )
    print(args.output / "comparison.json")


if __name__ == "__main__":
    main()
