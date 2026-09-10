"""Matched comparison and slices for the cross-division state candidate."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from epl_forecast.evaluation import paired_comparison
from epl_forecast.storage import write_json

OUTCOME_KEY = {"H": "p_home", "D": "p_draw", "A": "p_away"}
PAIRS = (
    ("M5-uncentered-bridge-control", "M9-cross-division-goals"),
    ("M5-centered-poisson-control", "M9-cross-division-goals"),
    ("M7-xg-v1", "M9-cross-division-xg"),
    ("M2-attack-defense-v1", "M9-cross-division-xg"),
    ("M9-cross-division-goals", "M9-cross-division-xg"),
    ("M9-cross-division-goals", "M10-division-map-goals"),
    ("M9-cross-division-xg", "M10-division-map-xg"),
    ("M5-centered-poisson-control", "M10-division-map-goals"),
    ("M7-xg-v1", "M10-division-map-xg"),
    ("M2-attack-defense-v1", "M10-division-map-xg"),
    ("M10-division-map-goals", "M10-division-map-xg"),
)


def outcome_loss(row):
    return -np.log(max(float(row[OUTCOME_KEY[row["outcome"]]]), 1e-15))


def slices(rows):
    """Promoted clubs are the population the cross-division state is meant to serve."""
    by_season = defaultdict(set)
    for row in rows:
        by_season[row["season_id"]].update([row["home_team_id"], row["away_team_id"]])
    order = sorted(by_season)
    promoted = {
        season: (by_season[season] - by_season[order[index - 1]]) if index else set()
        for index, season in enumerate(order)
    }
    first_five = defaultdict(lambda: defaultdict(int))
    opening = set()
    for row in sorted(rows, key=lambda r: (r["match_date"], r["match_id"])):
        if row["model_id"] != rows[0]["model_id"]:
            continue
        for team in (row["home_team_id"], row["away_team_id"]):
            first_five[row["season_id"]][team] += 1
            if first_five[row["season_id"]][team] <= 5:
                opening.add(row["match_id"])
    return {
        "all": lambda r: True,
        "promoted": lambda r: bool(
            promoted[r["season_id"]] & {r["home_team_id"], r["away_team_id"]}
        ),
        "established": lambda r: (
            not (promoted[r["season_id"]] & {r["home_team_id"], r["away_team_id"]})
        ),
        "opening": lambda r: r["match_id"] in opening,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260909)
    args = parser.parse_args()
    rows = list(csv.DictReader(open(args.run / "predictions.csv")))
    models = sorted({row["model_id"] for row in rows})
    tests = slices(rows)
    report = {"run": str(args.run), "models": models, "slices": {}}
    for name, predicate in tests.items():
        subset = [row for row in rows if predicate(row)]
        grouped = defaultdict(list)
        for row in subset:
            grouped[row["model_id"]].append(row)
        block = {
            "fixtures": len(grouped[models[0]]),
            "outcome_loss": {
                model: float(np.mean([outcome_loss(r) for r in group]))
                for model, group in sorted(grouped.items())
            },
            "paired": [],
        }
        for reference, candidate in PAIRS:
            if reference in grouped and candidate in grouped:
                block["paired"].append(
                    paired_comparison(
                        grouped[reference], grouped[candidate], args.samples, args.seed
                    )
                )
        report["slices"][name] = block
    output = args.output or args.run / "cross_division_report.json"
    write_json(output, report)
    for name, block in report["slices"].items():
        print(f"== {name} (n={block['fixtures']})")
        for model, value in block["outcome_loss"].items():
            print(f"   {model:32s} {value:.5f}")
        for pair in block["paired"]:
            print(
                f"   {pair['candidate']} - {pair['reference']}:"
                f" {pair['delta_log_loss']:+.5f}"
                f" [{pair['ci_lower']:+.5f}, {pair['ci_upper']:+.5f}]"
            )
    print(json.dumps({"written": str(output)}))


if __name__ == "__main__":
    main()
