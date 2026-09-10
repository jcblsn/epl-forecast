"""Team-matched distribution comparisons for current season projections."""

import numpy as np


def interval_width(row, target, level=90):
    interval = row[f"{target}_intervals"][str(level)]
    return interval[1] - interval[0]


def rank_distances(candidate, baseline):
    p = np.asarray(candidate["position_probabilities"])
    q = np.asarray(baseline["position_probabilities"])
    return float(np.abs(p.cumsum() - q.cumsum()).sum()), float(np.abs(p - q).sum() / 2)


def compare_forecasts(candidate, baseline, names, variant):
    base = {row["team_id"]: row for row in baseline["teams"]}
    rows = []
    for row in candidate["teams"]:
        reference = base[row["team_id"]]
        wasserstein, total_variation = rank_distances(row, reference)
        comparison = {
            "competition_id": candidate["competition_id"],
            "season_id": candidate["season_id"],
            "forecast_timestamp": candidate["results_observed_at"],
            "team_id": row["team_id"],
            "team_name": names[row["team_id"]],
            "variant": variant,
            "expected_rank_change": row["mean_position"] - reference["mean_position"],
            "rank_interval_50_width_change": interval_width(row, "position", 50)
            - interval_width(reference, "position", 50),
            "rank_interval_80_width_change": interval_width(row, "position", 80)
            - interval_width(reference, "position", 80),
            "rank_interval_90_width_change": interval_width(row, "position", 90)
            - interval_width(reference, "position", 90),
            "rank_wasserstein": wasserstein,
            "rank_total_variation": total_variation,
        }
        for key in sorted(k for k in row if k.endswith("_probability")):
            if key in reference:
                comparison[f"{key}_change"] = row[key] - reference[key]
        rows.append(comparison)
    return rows


def noise_flags(rows, noise_rows):
    noise = {(row["competition_id"], row["team_id"]): row for row in noise_rows}
    for row in rows:
        reference = noise[row["competition_id"], row["team_id"]]
        row["rank_wasserstein_exceeds_mc_noise"] = (
            row["rank_wasserstein"] > reference["rank_wasserstein"]
        )
        row["rank_total_variation_exceeds_mc_noise"] = (
            row["rank_total_variation"] > reference["rank_total_variation"]
        )
        row["expected_rank_change_exceeds_mc_noise"] = abs(row["expected_rank_change"]) > abs(
            reference["expected_rank_change"]
        )
        for key in [key for key in row if key.endswith("_probability_change")]:
            row[f"{key}_exceeds_mc_noise"] = abs(row[key]) > abs(reference.get(key, 0))
