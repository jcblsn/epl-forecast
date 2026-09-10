"""Coverage and cross-provider agreement for API-Football team match statistics.

Before any of these fields can be treated as current-strength information they have
to describe the same matches the retained providers describe. Shots and shots on
target are already carried by football-data, and Premier League xG by Understat, so
those overlaps are a validity check with a known answer; expected goals in the
Championship has no retained comparator and is exactly the gap this table fills.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance, write_csv
from epl_forecast.datasets import Dataset
from epl_forecast.storage import write_json

FIELDS = (
    "expected_goals",
    "goals_prevented",
    "shots_total",
    "shots_on_goal",
    "shots_inside_box",
    "shots_outside_box",
    "shots_blocked",
    "corners",
    "possession",
    "goalkeeper_saves",
    "passes_total",
    "passes_accurate",
    "fouls",
    "offsides",
    "yellow_cards",
    "red_cards",
)


def agreement(pairs):
    """Paired agreement between two providers measuring the same quantity."""
    if len(pairs) < 2:
        return {"team_matches": len(pairs)}
    left = np.array([p[0] for p in pairs], dtype=float)
    right = np.array([p[1] for p in pairs], dtype=float)
    difference = left - right
    return {
        "team_matches": len(pairs),
        "identical_share": float(np.mean(np.isclose(difference, 0))),
        "mean_difference": float(difference.mean()),
        "mean_absolute_difference": float(np.abs(difference).mean()),
        "rmse": float(np.sqrt(np.mean(difference**2))),
        "correlation": float(np.corrcoef(left, right)[0, 1]),
        "left_mean": float(left.mean()),
        "right_mean": float(right.mean()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = Dataset(args.data)
    try:
        statistics = data.rows("SELECT * FROM team_statistics")
        process = data.rows("SELECT * FROM team_process")
        fixtures = data.rows(
            "SELECT match_id, competition_id, season_id, status FROM fixtures WHERE stage='regular'"
        )
        provenance = data.provenance()
    finally:
        data.close()

    finished, season_of = defaultdict(set), {}
    for row in fixtures:
        if row["status"] == "finished":
            finished[row["competition_id"], row["season_id"]].add(row["match_id"])
            season_of[row["match_id"]] = (row["competition_id"], row["season_id"])
    # Coverage compares like with like: only statistics for finished regular-season
    # matches count, against the finished regular-season matches of the same season.
    outside = [r for r in statistics if r["match_id"] not in season_of]
    statistics = [r for r in statistics if r["match_id"] in season_of]
    indexed = {(r["match_id"], r["team_id"]): r for r in statistics}
    retained = defaultdict(dict)
    for row in process:
        retained[row["match_id"], row["team_id"]][row["provider"]] = row

    seasons = defaultdict(lambda: {"team_matches": 0, "matches": set()})
    field_counts = defaultdict(lambda: defaultdict(int))
    basis = defaultdict(int)
    for row in statistics:
        key = row["competition_id"], row["season_id"]
        seasons[key]["team_matches"] += 1
        seasons[key]["matches"].add(row["match_id"])
        basis[row["evidence_basis"]] += 1
        for field in FIELDS:
            if row[field] is not None:
                field_counts[key][field] += 1

    coverage = []
    for key in sorted(seasons):
        played = len(finished.get(key, ()))
        row = {
            "competition_id": key[0],
            "season_id": key[1],
            "finished_matches": played,
            "matches_with_statistics": len(seasons[key]["matches"]),
            "match_coverage": len(seasons[key]["matches"]) / played if played else None,
            "team_matches": seasons[key]["team_matches"],
        }
        for field in FIELDS:
            row[f"{field}_share"] = (
                field_counts[key][field] / seasons[key]["team_matches"]
                if seasons[key]["team_matches"]
                else None
            )
        coverage.append(row)

    comparisons = []
    for competition in sorted({r["competition_id"] for r in statistics}):
        for field, provider, other in (
            ("shots_total", "football_data", "shots"),
            ("shots_on_goal", "football_data", "shots_on_target"),
            ("expected_goals", "understat", "xg"),
        ):
            pairs = [
                (row[field], retained[key][provider][other])
                for key, row in indexed.items()
                if row["competition_id"] == competition
                and row[field] is not None
                and provider in retained.get(key, {})
                and retained[key][provider][other] is not None
            ]
            comparisons.append(
                {
                    "competition_id": competition,
                    "api_football_field": field,
                    "comparator": f"{provider}.{other}",
                    **agreement(pairs),
                }
            )

    report = {
        "execution": execution_provenance(),
        "data_manifest_batches": len(provenance["batches"]),
        "team_matches": len(statistics),
        "evidence_basis": dict(sorted(basis.items())),
        "scope": (
            "Finished regular-season team-matches only, in both the numerator and the "
            "denominator; playoff and unfinished fixtures are excluded from each"
        ),
        "team_matches_outside_finished_regular_season": len(outside),
        "coverage": coverage,
        "provider_agreement": comparisons,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "audit.json", report)
    write_csv(
        args.output / "coverage.csv",
        list(coverage[0]) if coverage else ["competition_id"],
        coverage,
    )
    write_csv(
        args.output / "provider_agreement.csv",
        list(comparisons[0]) if comparisons else ["competition_id"],
        comparisons,
    )
    print(args.output / "audit.json")


if __name__ == "__main__":
    main()
