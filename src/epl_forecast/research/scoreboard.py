"""Matched match-forecast scoreboard from retained prediction artifacts."""

from collections import defaultdict

import numpy as np

from epl_forecast.evaluation import metrics


def _index(rows):
    groups = defaultdict(dict)
    for row in rows:
        key = row["match_id"]
        model = row["model_id"]
        if key in groups[model]:
            raise ValueError(f"Duplicate scoreboard prediction: {model} {key}")
        groups[model][key] = row
    return groups


def build_scoreboard(
    predictions,
    markets,
    candidate_ids,
    reference_id,
    preclosing_id,
    closing_id,
    retained_ids,
    bins=10,
):
    """Score selected models on their exact common fixture population."""
    structural = _index(predictions)
    market = _index(markets)
    if len(candidate_ids) != len(set(candidate_ids)) or not candidate_ids:
        raise ValueError("Candidate model IDs must be nonempty and unique")
    required = [reference_id, *candidate_ids, *retained_ids]
    missing = sorted(set(required) - structural.keys())
    missing += sorted({preclosing_id, closing_id} - market.keys())
    if missing:
        raise ValueError(f"Scoreboard models are missing: {missing}")
    selected_ids = list(dict.fromkeys([reference_id, *candidate_ids]))
    all_groups = {model: structural[model] for model in selected_ids}
    all_groups |= {preclosing_id: market[preclosing_id], closing_id: market[closing_id]}
    matched_ids = set.intersection(*(set(rows) for rows in all_groups.values()))
    if not matched_ids:
        raise ValueError("Scoreboard models have no common fixtures")
    ordered_ids = sorted(matched_ids)
    outcomes = {group[key]["outcome"] for group in all_groups.values() for key in ordered_ids}
    if len(outcomes) > 3 or any(
        len({group[key]["outcome"] for group in all_groups.values()}) != 1 for key in ordered_ids
    ):
        raise ValueError("Scoreboard models disagree on observed outcomes")

    overall, by_season, calibration = [], [], []
    scored = {}
    for model, group in all_groups.items():
        rows = [group[key] for key in ordered_ids]
        summary, model_calibration = metrics(rows, bins)
        scored[model] = summary
        overall.append({"model_id": model, **summary})
        calibration.extend({"model_id": model, **row} for row in model_calibration)
        for season in sorted({row["season_id"] for row in rows}):
            season_summary, _ = metrics([row for row in rows if row["season_id"] == season], bins)
            by_season.append({"model_id": model, "season_id": season, **season_summary})

    best_retained = min(retained_ids, key=lambda model: scored[model]["log_loss"])
    reference_loss = scored[reference_id]["log_loss"]
    preclosing_gap = reference_loss - scored[preclosing_id]["log_loss"]
    closing_gap = reference_loss - scored[closing_id]["log_loss"]
    if preclosing_gap <= 0 or closing_gap <= 0:
        raise ValueError("Market comparators must outperform the reference on matched fixtures")
    comparisons = []
    for candidate in candidate_ids:
        delta_reference = scored[candidate]["log_loss"] - reference_loss
        comparisons.append(
            {
                "candidate": candidate,
                "matched_fixtures": len(ordered_ids),
                "best_retained_structural_model": best_retained,
                "candidate_minus_m2_log_loss": delta_reference,
                "candidate_minus_best_retained_structural_log_loss": scored[candidate]["log_loss"]
                - scored[best_retained]["log_loss"],
                "preclosing_market_minus_m2_log_loss": -preclosing_gap,
                "closing_market_minus_m2_log_loss": -closing_gap,
                "fraction_m2_to_preclosing_market_gap_closed": -delta_reference / preclosing_gap,
                "fraction_m2_to_closing_market_gap_closed": -delta_reference / closing_gap,
                "geometric_realized_probability_change_vs_m2": np.expm1(-delta_reference),
            }
        )
    return {
        "matched_fixture_ids": ordered_ids,
        "overall": overall,
        "by_season": by_season,
        "calibration": calibration,
        "comparisons": comparisons,
        "best_retained_structural_model": best_retained,
    }
