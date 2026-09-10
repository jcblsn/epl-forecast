"""Cheap residual-signal diagnostics over retained match forecasts."""

import math

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from epl_forecast.evaluation import individual_metrics
from epl_forecast.schema import OUTCOMES


def low_score_adjustment(row, rho):
    home_rate = float(row["expected_home_goals"])
    away_rate = float(row["expected_away_goals"])
    factors = {
        (0, 0): 1 - home_rate * away_rate * rho,
        (0, 1): 1 + home_rate * rho,
        (1, 0): 1 + away_rate * rho,
        (1, 1): 1 - rho,
    }
    if min(factors.values()) <= 0:
        raise ValueError("Low-score correction produced a nonpositive probability")

    def poisson(x, rate):
        return math.exp(-rate) * rate**x / math.factorial(x)

    deltas = {
        score: poisson(score[0], home_rate) * poisson(score[1], away_rate) * (factor - 1)
        for score, factor in factors.items()
    }
    probabilities = np.array([row[f"p_{side}"] for side in ("home", "draw", "away")], dtype=float)
    probabilities += [deltas[1, 0], deltas[0, 0] + deltas[1, 1], deltas[0, 1]]
    if (probabilities <= 0).any() or not np.isclose(probabilities.sum(), 1, atol=1e-10):
        raise ValueError("Low-score adjustment violated outcome probability conservation")
    score = int(row["home_goals"]), int(row["away_goals"])
    score_log_probability = float(row["score_log_probability"])
    if score in factors:
        score_log_probability += math.log(factors[score])
    return probabilities, score_log_probability


def fit_low_score_rho(rows, bound=0.15):
    if not rows:
        raise ValueError("Low-score fit requires predictions")

    def objective(rho):
        try:
            return -float(np.mean([low_score_adjustment(row, rho)[1] for row in rows]))
        except ValueError:
            return 1e6

    interior = minimize_scalar(objective, bounds=(-bound, bound), method="bounded")
    choices = [
        (-bound, objective(-bound)),
        (bound, objective(bound)),
        (float(interior.x), interior.fun),
    ]
    rho, score_nll = min(choices, key=lambda pair: pair[1])
    return {"rho": rho, "matches": len(rows), "score_nll": float(score_nll)}


def score_low_score(rows, rho):
    probabilities, score_logs = [], []
    outcomes = []
    for row in rows:
        p, score_log = low_score_adjustment(row, rho)
        probabilities.append(p)
        score_logs.append(score_log)
        outcomes.append(OUTCOMES.index(row["outcome"]))
    loss, brier = individual_metrics(np.asarray(probabilities), np.asarray(outcomes))
    return {
        "matches": len(rows),
        "log_loss": float(loss.mean()),
        "brier": float(brier.mean()),
        "score_nll": -float(np.mean(score_logs)),
    }


def scouting_features(rows_by_model, match_ids):
    features = []
    for match_id in match_ids:
        m2 = rows_by_model["M2-attack-defense-v1"][match_id]
        m5 = rows_by_model["M5-quality-tilt-poisson"][match_id]
        m7 = rows_by_model["M7-xg-v1"][match_id]
        probabilities = [
            np.array([row[f"p_{side}"] for side in ("home", "draw", "away")], dtype=float)
            for row in (m2, m5, m7)
        ]
        difference = probabilities[2] - probabilities[0]
        base = np.concatenate([*(np.log(p) - np.log(p).mean() for p in probabilities), difference])
        total = float(m7["expected_home_goals"]) + float(m7["expected_away_goals"])
        gap = float(m7["expected_home_goals"]) - float(m7["expected_away_goals"])
        uncertainty = float(m7["log_home_rate_variance"]) + float(m7["log_away_rate_variance"])
        quality_gap = float(m7["home_quality"]) - float(m7["away_quality"])
        tilt_sum = float(m7["home_tilt"]) + float(m7["away_tilt"])
        features.append(
            np.concatenate(
                [
                    base,
                    difference**2,
                    [total, total**2, gap, gap**2, uncertainty, quality_gap, tilt_sum],
                ]
            )
        )
    return np.asarray(features)


def fit_multinomial(features, outcomes, ridge=10.0):
    x = np.asarray(features, dtype=float)
    y = np.asarray(outcomes, dtype=int)
    if x.ndim != 2 or y.shape != (len(x),) or len(x) < 3 or not np.isfinite(x).all():
        raise ValueError("Invalid scouting-model training data")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-8] = 1
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])

    def objective(flat):
        beta = flat.reshape(design.shape[1], 2)
        logits = np.column_stack([design @ beta, np.zeros(len(design))])
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        loss = -np.log(probabilities[np.arange(len(y)), y]).sum()
        penalty = 0.5 * ridge * np.sum(beta[1:] ** 2)
        residual = probabilities - np.eye(3)[y]
        gradient = design.T @ residual[:, :2]
        gradient[1:] += ridge * beta[1:]
        return float(loss + penalty), gradient.ravel()

    result = minimize(
        objective,
        np.zeros(design.shape[1] * 2),
        jac=True,
        method="L-BFGS-B",
        options={"ftol": 1e-12, "gtol": 1e-7, "maxiter": 1000},
    )
    if not result.success:
        raise RuntimeError(f"Scouting model failed: {result.message}")
    return {
        "mean": mean,
        "scale": scale,
        "beta": result.x.reshape(design.shape[1], 2),
        "ridge": ridge,
    }


def predict_multinomial(fit, features):
    x = (np.asarray(features, dtype=float) - fit["mean"]) / fit["scale"]
    design = np.column_stack([np.ones(len(x)), x])
    logits = np.column_stack([design @ fit["beta"], np.zeros(len(design))])
    logits -= logits.max(axis=1, keepdims=True)
    probabilities = np.exp(logits)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


def market_disagreement_features(structural_row, market_row):
    structural = np.array(
        [structural_row[f"p_{side}"] for side in ("home", "draw", "away")], dtype=float
    )
    market = np.array([market_row[f"p_{side}"] for side in ("home", "draw", "away")], dtype=float)
    return {
        "market_minus_structural_home": float(market[0] - structural[0]),
        "market_minus_structural_draw": float(market[1] - structural[1]),
        "market_minus_structural_away": float(market[2] - structural[2]),
        "expected_total_goals": float(structural_row["expected_home_goals"])
        + float(structural_row["expected_away_goals"]),
        "expected_goal_difference": float(structural_row["expected_home_goals"])
        - float(structural_row["expected_away_goals"]),
        "quality_gap": float(structural_row["home_quality"])
        - float(structural_row["away_quality"]),
        "tilt_sum": float(structural_row["home_tilt"]) + float(structural_row["away_tilt"]),
        "rate_uncertainty": float(structural_row["log_home_rate_variance"])
        + float(structural_row["log_away_rate_variance"]),
        "structural_entropy": float(-(structural * np.log(structural)).sum()),
    }
