"""Check that carrying latent states into the bracket moves only the bracket.

The correction is meant to be surgical. A simulated path's regular season is already
finished when the playoffs start, so conditioning the bracket on that path's own
latent state cannot touch its points, its rank, or anything derived from the table.
If a points or rank distribution moves at all, the two runs are not sharing the
draws they are supposed to share and the comparison is invalid.

What may move is promotion. Under the old behaviour every tie was resampled from the
league-wide forecast distribution, which discards the strength that put a club in the
playoffs in the first place; under the correction a club that qualified because it
was drawn strong plays the bracket strong. The expected direction is that promotion
mass concentrates on clubs whose playoff qualification comes with high strength. A
very large move is worth reading as a possible defect rather than a result, so the
biggest are listed.
"""

import argparse
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance, write_csv
from epl_forecast.cli import fitted_model, load_config
from epl_forecast.datasets import Dataset, timestamp
from epl_forecast.live import LONDON, load_live_season
from epl_forecast.research.uncertainty_ladder import MatchedStateMixture
from epl_forecast.sanctions import load_registry
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import write_json

COMPETITION = "eng-championship"
MODEL_ID = "M7-xg-v1"
EVENTS = (
    "automatic_promotion_probability",
    "playoff_qualification_probability",
    "playoff_promotion_probability",
    "promotion_probability",
    "relegation_probability",
    "title_probability",
)


def distribution_distance(left, right):
    keys = sorted(set(left) | set(right), key=int)
    a = np.array([left.get(k, 0.0) for k in keys])
    b = np.array([right.get(k, 0.0) for k in keys])
    return float(np.abs(a - b).max())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", type=timestamp, required=True)
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--simulations", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--flag-threshold", type=float, default=0.05)
    args = parser.parse_args()
    cutoff_day = args.cutoff.astimezone(LONDON).date()
    data = Dataset(args.data, args.cutoff)
    try:
        matches = data.matches()
        provenance = data.provenance()
        sanctions = load_registry(data)
    finally:
        data.close()
    live = load_live_season(args.data, args.cutoff, COMPETITION, args.season)
    config = load_config(Path("configs/xg_quality_tilt.toml"))
    config["competition_id"] = COMPETITION
    for spec in config["models"]:
        spec.setdefault("parameters", {})["competition_id"] = COMPETITION
        if spec["id"] == MODEL_ID:
            spec["parameters"]["data_cutoff"] = args.cutoff.isoformat()
    model, _, _ = fitted_model(matches, config, MODEL_ID, cutoff_day)
    adjustments = sanctions.known_adjustments(COMPETITION, args.season, cutoff_day)

    forecasts = {}
    for conditioning in ("path", "marginal"):
        forecasts[conditioning] = simulate_season(
            MatchedStateMixture(model, live.teams, args.season),
            live.played,
            live.remaining,
            list(live.teams),
            cutoff_day,
            args.simulations,
            args.seed,
            adjustments,
            results_observed_at=live.observed_at,
            playoff_conditioning=conditioning,
        )

    rows = []
    for path_row, marginal_row in zip(
        sorted(forecasts["path"]["teams"], key=lambda r: r["team_id"]),
        sorted(forecasts["marginal"]["teams"], key=lambda r: r["team_id"]),
        strict=True,
    ):
        row = {
            "team_id": path_row["team_id"],
            "team_name": live.teams[path_row["team_id"]],
            "points_pmf_max_difference": distribution_distance(
                path_row["points_distribution"], marginal_row["points_distribution"]
            ),
            "rank_pmf_max_difference": float(
                np.abs(
                    np.array(path_row["position_probabilities"])
                    - np.array(marginal_row["position_probabilities"])
                ).max()
            ),
            "mean_points_difference": path_row["mean_points"] - marginal_row["mean_points"],
        }
        for event in EVENTS:
            row[f"{event}_marginal"] = marginal_row[event]
            row[f"{event}_path"] = path_row[event]
            row[f"{event}_change"] = path_row[event] - marginal_row[event]
        rows.append(row)

    regular_season_invariant = all(
        row["points_pmf_max_difference"] == 0
        and row["rank_pmf_max_difference"] == 0
        and row["mean_points_difference"] == 0
        for row in rows
    )
    movers = sorted(rows, key=lambda r: -abs(r["promotion_probability_change"]))
    flagged = [r for r in movers if abs(r["promotion_probability_change"]) > args.flag_threshold]
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "playoff_conditioning.csv", list(rows[0]), rows)
    write_json(
        args.output / "validation.json",
        {
            "execution": execution_provenance(),
            "competition_id": COMPETITION,
            "season_id": args.season,
            "forecast_timestamp": args.cutoff.isoformat(),
            "simulations": args.simulations,
            "seed": args.seed,
            "data_manifest_count": len(provenance["batches"]),
            "point_adjustments": adjustments,
            "regular_season_invariant": regular_season_invariant,
            "max_points_pmf_difference": max(r["points_pmf_max_difference"] for r in rows),
            "max_rank_pmf_difference": max(r["rank_pmf_max_difference"] for r in rows),
            "total_promotion_mass_path": sum(r["promotion_probability_path"] for r in rows),
            "total_promotion_mass_marginal": sum(r["promotion_probability_marginal"] for r in rows),
            "mean_absolute_promotion_change": float(
                np.mean([abs(r["promotion_probability_change"]) for r in rows])
            ),
            "largest_promotion_changes": [
                {
                    "team_id": r["team_id"],
                    "marginal": r["promotion_probability_marginal"],
                    "path": r["promotion_probability_path"],
                    "change": r["promotion_probability_change"],
                    "playoff_qualification": r["playoff_qualification_probability_path"],
                }
                for r in movers[:6]
            ],
            "flag_threshold": args.flag_threshold,
            "flagged_for_investigation": [r["team_id"] for r in flagged],
        },
    )
    print(args.output / "validation.json")
    if not regular_season_invariant:
        raise SystemExit("Regular-season distributions moved; the two runs are not matched")


if __name__ == "__main__":
    main()
