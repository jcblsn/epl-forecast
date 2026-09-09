"""Explain why a player estimate is where it is, rather than only reporting a mean.

Every number a candidate produces is traced back to the evidence that moved it: the
recent and long process values, the contribution of each feature, the exposure behind
each of them, and the two separate sources of uncertainty. Shared mapping uncertainty
is common to all players and largely cancels in a comparison; player-local uncertainty
does not, so the two are never merged into a single band.
"""

import math

import numpy as np

from epl_forecast.research.player_layer import (
    CANDIDATES,
    LEAGUE_REFERENCE_XG,
    PROCESS_MARKS,
    design,
)
from epl_forecast.research.player_layer_evaluation import _apply, _matrix


def local_log_sd(state, mark, block):
    """Posterior log-rate spread of the player's own shrunk estimate.

    Gamma-Poisson with the population variance-to-mean ratio as the dispersion, so a
    player with little retained exposure keeps a visibly wider estimate.
    """
    pool = state.population[mark]
    dispersion = max(pool["dispersion"], 1e-3)
    prior_mean = pool["by_role"].get(state.role, pool["league"])
    if block in ("long_share", "recent_share") and mark in PROCESS_MARKS:
        key = mark if block == "long_share" else f"recent_{mark}"
        entry = state.share[key]
        strength = 10.0 * LEAGUE_REFERENCE_XG
        shape = (entry["share"] * (entry["opportunity"] + strength)) / dispersion
    else:
        window = state.long if block.startswith("long") else state.recent
        entry = window[mark]
        shape = (entry["total"] + 10.0 * prior_mean) / dispersion
    return float(math.sqrt(1.0 / max(shape, 1e-6)))


def decompose(model, state, candidate, mark, exposure=1.0):
    """Feature contributions and the uncertainty budget for one player at one cutoff."""
    names, values = design(state, candidate, mark)
    standardized = (values - model["centre"]) / model["scale"] if len(names) else values
    vector = np.concatenate([[1.0], standardized])
    beta = model["beta"]
    pool = state.population[mark]
    prior_mean = pool["by_role"].get(state.role, pool["league"])
    offset = math.log(max(prior_mean, 1e-4)) + math.log(max(exposure, 1e-6))
    contributions = [
        {
            "feature": name,
            "raw_value": float(values[index]),
            "standardized_value": float(standardized[index]),
            "coefficient": float(beta[index + 1]),
            "log_contribution": float(beta[index + 1] * standardized[index]),
        }
        for index, name in enumerate(names)
    ]
    mapping_variance = float(vector @ model["covariance"] @ vector)
    local_variance = 0.0
    for index, name in enumerate(names):
        block = (
            "long_share"
            if name == "long_share"
            else "recent_share"
            if name == "recent_share"
            else "long_rate"
            if name.startswith(("long", "api_long"))
            else "recent_rate"
            if name.startswith(("recent", "api_recent"))
            else None
        )
        if block is None:
            continue
        source = (
            mark
            if name in ("long_rate", "recent_rate", "long_share", "recent_share")
            else name.split("_", 2)[-1]
        )
        if source not in state.population:
            source = mark
        scaled = beta[index + 1] / model["scale"][index]
        local_variance += float((scaled * local_log_sd(state, source, block)) ** 2)
    log_mean = float(vector @ beta) + offset
    return {
        "player_id": state.player_id,
        "player_name": state.player_name,
        "cutoff": str(state.cutoff),
        "role": state.role,
        "club": state.club,
        "target_club": state.target_club,
        "candidate": candidate,
        "mark": mark,
        "role_population_rate": float(prior_mean),
        "estimated_rate_per_90": float(math.exp(log_mean - math.log(max(exposure, 1e-6)))),
        "role_relative": float(math.exp(vector @ beta)),
        "contributions": contributions,
        "intercept": float(beta[0]),
        "uncertainty": {
            "mapping_log_sd": math.sqrt(mapping_variance),
            "player_local_log_sd": math.sqrt(local_variance),
            "total_log_sd": math.sqrt(mapping_variance + local_variance),
        },
        "evidence": {
            "long_effective_matches": state.long[mark]["exposure"],
            "recent_effective_matches": state.recent[mark]["exposure"],
            "long_total": state.long[mark]["total"],
            "recent_total": state.recent[mark]["total"],
            "long_raw_rate": state.long[mark]["raw_rate"],
            "recent_raw_rate": state.recent[mark]["raw_rate"],
            "long_appearances": state.long[mark]["appearances"],
            "api_appearances": state.api["appearances"],
            "staleness_days": state.staleness,
            "player_environment_xg": state.environment["player"],
            "current_club_environment": (state.environment["current_club"] or {}).get("rate"),
            "target_club_environment": (state.environment["target_club"] or {}).get("rate"),
            "share": state.share.get(mark),
        },
    }


def compare(model, left, right, candidate, mark):
    """Direct pairwise difference; overlapping marginal bands are not a comparison."""
    names, left_values = design(left, candidate, mark)
    _, right_values = design(right, candidate, mark)
    scale = model["scale"] if len(names) else np.ones(0)
    left_vector = np.concatenate([[1.0], (left_values - model["centre"]) / scale])
    right_vector = np.concatenate([[1.0], (right_values - model["centre"]) / scale])
    difference = left_vector - right_vector
    mapping_variance = float(difference @ model["covariance"] @ difference)
    left_decomposition = decompose(model, left, candidate, mark)
    right_decomposition = decompose(model, right, candidate, mark)
    local_variance = (
        left_decomposition["uncertainty"]["player_local_log_sd"] ** 2
        + right_decomposition["uncertainty"]["player_local_log_sd"] ** 2
    )
    mean = float(difference @ model["beta"])
    sd = math.sqrt(mapping_variance + local_variance)
    return {
        "left": left.player_name or left.player_id,
        "right": right.player_name or right.player_id,
        "candidate": candidate,
        "mark": mark,
        "log_ratio": mean,
        "ratio": float(math.exp(mean)),
        "mapping_log_sd": math.sqrt(mapping_variance),
        "player_local_log_sd": math.sqrt(local_variance),
        "log_sd": sd,
        "interval_95": [float(math.exp(mean - 1.96 * sd)), float(math.exp(mean + 1.96 * sd))],
        "separated": bool(abs(mean) > 1.96 * sd),
    }


def estimate_table(model, states, candidate, mark):
    if not states:
        return []
    _, matrix = _matrix([{"state": s, "target_exposure": 1.0} for s in states], candidate, mark)
    offset = np.array(
        [
            math.log(
                max(s.population[mark]["by_role"].get(s.role, s.population[mark]["league"]), 1e-4)
            )
            for s in states
        ]
    )
    mean, _ = _apply(model, matrix, offset)
    rows = []
    for state, value in zip(states, mean, strict=True):
        decomposition = decompose(model, state, candidate, mark)
        rows.append(
            {
                "player_id": state.player_id,
                "player_name": state.player_name,
                "role": state.role,
                "club": state.club,
                "candidate": candidate,
                "mark": mark,
                "rate_per_90": float(value),
                "role_relative": decomposition["role_relative"],
                "mapping_log_sd": decomposition["uncertainty"]["mapping_log_sd"],
                "player_local_log_sd": decomposition["uncertainty"]["player_local_log_sd"],
                "total_log_sd": decomposition["uncertainty"]["total_log_sd"],
                "long_effective_matches": decomposition["evidence"]["long_effective_matches"],
                "staleness_days": decomposition["evidence"]["staleness_days"],
            }
        )
    return sorted(rows, key=lambda r: -r["rate_per_90"])


CANDIDATE_ORDER = tuple(CANDIDATES)
