"""Fitted division level and home advantage over time from the cross-division state."""

import argparse
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, provenance
from epl_forecast.datasets import Dataset, load_dataset
from epl_forecast.models.cross_division import CrossDivisionQualityTilt, CrossDivisionXG
from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.storage import write_json

DYNAMICS = {
    "quality_retention": 0.85,
    "quality_sd": 0.09,
    "tilt_retention": 0.5,
    "tilt_sd": 0.07,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2017, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 1))
    args = parser.parse_args()
    new_run_directory(args.output)
    matches, _, manifest = load_dataset(args.data)
    data = Dataset(args.data)
    try:
        observations = data.process()
    finally:
        data.close()
    eligible = [m for m in matches if m.fixture.competition_id in (PL, CHAMPIONSHIP)]
    models = {
        "goals_only": CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS),
        "goals_xg": CrossDivisionXG(observations, 0.2, **DYNAMICS),
    }
    cutoffs = []
    day = date(args.start.year, 1, 1)
    while day < args.end:
        cutoffs.append(day)
        day = date(day.year + (day.month == 7), 7 if day.month == 1 else 1, 1)
    path = []
    for cutoff in cutoffs:
        training = [m for m in eligible if m.available_on <= cutoff]
        if len(training) < 400:
            continue
        for name, model in models.items():
            model.fit(training, cutoff)
            summary = model.division_summary()
            path.append(
                {
                    "model": name,
                    "as_of": str(cutoff),
                    "training_matches": len(training),
                    **summary,
                    "crossed_divisions": len(summary["crossed_divisions"]),
                }
            )
            print(
                f"{name:10s} {cutoff} level {summary['championship_level']:+.3f}"
                f" ±{summary['championship_level_sd']:.3f}"
                f" home {summary['home_advantage']:+.3f} ±{summary['home_advantage_sd']:.3f}"
                f" clubs {summary['clubs']}",
                flush=True,
            )
    drift = {}
    for name in models:
        values = np.array([row["home_advantage"] for row in path if row["model"] == name])
        levels = np.array([row["championship_level"] for row in path if row["model"] == name])
        drift[name] = {
            "home_advantage_first": float(values[0]),
            "home_advantage_last": float(values[-1]),
            "home_advantage_min": float(values.min()),
            "home_advantage_max": float(values.max()),
            "championship_level_first": float(levels[0]),
            "championship_level_last": float(levels[-1]),
            "championship_level_mean": float(levels.mean()),
        }
    report = {
        "config": {"start": str(args.start), "end": str(args.end), "dynamics": DYNAMICS},
        "path": path,
        "drift": drift,
    }
    write_json(args.output / "state_path.json", report)
    write_json(args.output / "provenance.json", provenance(report["config"], manifest))
    print(report["drift"], flush=True)


if __name__ == "__main__":
    main()
