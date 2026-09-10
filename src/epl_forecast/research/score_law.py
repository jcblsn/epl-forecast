"""One shared Gamma match-intensity score law against the independent Poisson control.

Both laws are applied to identical saved pre-match state distributions, so the
comparison isolates the score law and changes nothing about the states.
"""

import math
from datetime import date

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln, logsumexp

from epl_forecast.models.poisson import PoissonMixture
from epl_forecast.models.quality_tilt_scores import GammaPoissonMixture, joint_logpmf

BASELINES = ("M2-attack-defense-v1", "M5-centered-poisson-control", "M7-xg-v1")
OUTCOMES = ("H", "D", "A")
EVENTS = ("draw", "scoreless", "total_at_least_six", "both_teams_score")


def state_moments(row):
    """Saved Gaussian log-rate state; M2's point estimate is the zero-variance case."""
    if row["model_id"] == BASELINES[0]:
        mean = np.log([float(row["expected_home_goals"]), float(row["expected_away_goals"])])
        return mean, np.zeros((2, 2))
    # A single filter records no specification weight; a mixture must be collapsed to one.
    effective = row["effective_specifications"]
    if effective and not np.isclose(float(effective), 1.0, atol=1e-12, rtol=0):
        raise ValueError("A single effective Gaussian specification is required")
    cross = float(row["log_rate_covariance"])
    return (
        np.array([float(row["log_home_rate_mean"]), float(row["log_away_rate_mean"])]),
        np.array(
            [
                [float(row["log_home_rate_variance"]), cross],
                [cross, float(row["log_away_rate_variance"])],
            ]
        ),
    )


def distribution(row, dispersion=None, order=9):
    mean, covariance = state_moments(row)
    if dispersion is None:
        return PoissonMixture(mean, covariance, order)
    return GammaPoissonMixture(mean, covariance, order, dispersion)


class Quadrature:
    """Saved states expanded once so the dispersion search reuses the same nodes.

    Both laws mix conditional score probabilities over one Gaussian log-rate
    quadrature, and only the conditional part depends on the dispersion.
    """

    def __init__(self, rows, order=9):
        if not rows:
            raise ValueError("A quadrature needs at least one saved state")
        components = [distribution(row, order=order) for row in rows]
        self.home_rates = np.array([c.home_rates for c in components])
        self.away_rates = np.array([c.away_rates for c in components])
        self.log_weights = np.log(components[0].weights)
        self.home_goals = np.array([[int(row["home_goals"])] for row in rows])
        self.away_goals = np.array([[int(row["away_goals"])] for row in rows])

    def log_likelihood(self, dispersion):
        if dispersion is None:
            terms = (
                self.home_goals * np.log(self.home_rates)
                - self.home_rates
                - gammaln(self.home_goals + 1)
                + self.away_goals * np.log(self.away_rates)
                - self.away_rates
                - gammaln(self.away_goals + 1)
            )
        else:
            terms = joint_logpmf(
                self.home_goals, self.away_goals, self.home_rates, self.away_rates, dispersion
            )
        return float(np.sum(logsumexp(self.log_weights + terms, axis=1)))


def score_log_likelihood(rows, dispersion, order=9):
    return Quadrature(rows, order).log_likelihood(dispersion)


def fit_dispersion(rows, bounds=(1.0, 10000.0), order=9):
    """One shared Gamma tempo shape, chosen only by earlier score likelihood."""
    quadrature = Quadrature(rows, order)
    low, high = math.log(bounds[0]), math.log(bounds[1])
    result = minimize_scalar(
        lambda log_k: -quadrature.log_likelihood(math.exp(log_k)),
        bounds=(low, high),
        method="bounded",
        options={"xatol": 1e-4},
    )
    return {
        "dispersion": math.exp(result.x),
        "training_fixtures": len(rows),
        "at_boundary": bool(min(result.x - low, high - result.x) < 1e-3 * (high - low)),
        "poisson_log_likelihood": quadrature.log_likelihood(None),
        "gamma_log_likelihood": -float(result.fun),
    }


def case_scores(row, dispersion, order=9):
    outcome = OUTCOMES.index(row["outcome"])
    target = np.eye(3)[outcome]
    result = {}
    for variant, shape in (("poisson", None), ("shared_gamma", dispersion)):
        scores = distribution(row, shape, order)
        probabilities = np.asarray(scores.outcome_probabilities())
        result[variant] = {
            "score_nll": -scores.log_probability(int(row["home_goals"]), int(row["away_goals"])),
            "log_loss": -math.log(max(probabilities[outcome], 1e-15)),
            "brier": float(np.sum((probabilities - target) ** 2)),
            "p_home": float(probabilities[0]),
            "p_draw": float(probabilities[1]),
            "p_away": float(probabilities[2]),
        }
    return result


def chronological_score_law(rows, first_scored, minimum_training=200, order=9):
    """Refit the single dispersion at each cutoff on strictly earlier fixtures."""
    rows = sorted(rows, key=lambda row: (row["forecast_as_of"], row["match_id"]))
    predictions, fits, skipped = [], [], []
    cutoffs = sorted(
        {row["forecast_as_of"] for row in rows if row["forecast_as_of"] >= first_scored}
    )
    for cutoff in cutoffs:
        training = [row for row in rows if row["match_date"] < cutoff]
        targets = [row for row in rows if row["forecast_as_of"] == cutoff]
        if len(training) < minimum_training:
            skipped.append({"cutoff": cutoff, "training": len(training), "fixtures": len(targets)})
            continue
        fit = fit_dispersion(training, order=order)
        fits.append({"cutoff": cutoff, **fit})
        for row in targets:
            scores = case_scores(row, fit["dispersion"], order)
            for variant, values in scores.items():
                predictions.append(
                    {
                        "match_id": row["match_id"],
                        "season_id": row["season_id"],
                        "match_date": row["match_date"],
                        "forecast_as_of": row["forecast_as_of"],
                        "model_id": row["model_id"],
                        "variant": variant,
                        "dispersion": fit["dispersion"],
                        "home_goals": int(row["home_goals"]),
                        "away_goals": int(row["away_goals"]),
                        "outcome": row["outcome"],
                        **values,
                    }
                )
    return {"predictions": predictions, "fits": fits, "skipped": skipped}


def tail_events(row):
    home, away = int(row["home_goals"]), int(row["away_goals"])
    return {
        "draw": home == away,
        "scoreless": home + away == 0,
        "total_at_least_six": home + away >= 6,
        "both_teams_score": home > 0 and away > 0,
    }


def predicted_tail_events(row, dispersion, order=9, max_goals=24):
    scores = distribution(row, dispersion, order)
    grid, _ = scores.grid(max_goals)
    goals = np.arange(max_goals + 1)
    total = goals[:, None] + goals[None, :]
    return {
        "draw": float(np.sum(grid * (goals[:, None] == goals[None, :]))),
        "scoreless": float(grid[0, 0]),
        "total_at_least_six": float(np.sum(grid * (total >= 6))),
        "both_teams_score": float(np.sum(grid[1:, 1:])),
    }


def block_bootstrap(deltas, keys, samples=2000, seed=17):
    blocks = {}
    for key, delta in zip(keys, deltas, strict=True):
        blocks.setdefault(key, []).append(delta)
    values = list(blocks.values())
    sums = np.array([sum(v) for v in values])
    counts = np.array([len(v) for v in values])
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(values), size=(samples, len(values)))
    draws = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return {
        "difference": float(sums.sum() / counts.sum()),
        "interval": np.quantile(draws, [0.025, 0.975]).tolist(),
        "blocks": len(values),
    }


def calendar_week(row):
    return date.fromisoformat(row["match_date"]).isocalendar()[:2]


def summarize(predictions, model_id):
    rows = [row for row in predictions if row["model_id"] == model_id]
    paired = {}
    for row in rows:
        paired.setdefault(row["match_id"], {})[row["variant"]] = row
    if not paired:
        return {"fixtures": 0}
    result = {"fixtures": len(paired), "metrics": {}}
    for metric in ("score_nll", "log_loss", "brier"):
        deltas, keys = [], []
        for pair in paired.values():
            deltas.append(pair["shared_gamma"][metric] - pair["poisson"][metric])
            keys.append(calendar_week(pair["poisson"]))
        result["metrics"][metric] = {
            "poisson": float(np.mean([pair["poisson"][metric] for pair in paired.values()])),
            "shared_gamma": float(
                np.mean([pair["shared_gamma"][metric] for pair in paired.values()])
            ),
            **block_bootstrap(deltas, keys),
        }
    return result


def event_calibration(rows, predictions):
    """Match-level tail events: predicted mass, observed frequency and paired Brier."""
    dispersions = {
        (row["model_id"], row["match_id"]): row["dispersion"]
        for row in predictions
        if row["variant"] == "shared_gamma"
    }
    scored = [row for row in rows if (row["model_id"], row["match_id"]) in dispersions]
    result = {}
    for model_id in sorted({row["model_id"] for row in scored}):
        subset = [row for row in scored if row["model_id"] == model_id]
        predicted = {
            variant: [
                predicted_tail_events(
                    row,
                    dispersions[model_id, row["match_id"]] if variant == "shared_gamma" else None,
                )
                for row in subset
            ]
            for variant in ("poisson", "shared_gamma")
        }
        observed = [tail_events(row) for row in subset]
        block = {"fixtures": len(subset), "events": {}}
        for event in EVENTS:
            truth = np.array([float(row[event]) for row in observed])
            entry = {"observed": float(truth.mean())}
            briers = {}
            for variant in ("poisson", "shared_gamma"):
                mass = np.array([row[event] for row in predicted[variant]])
                entry[variant] = float(mass.mean())
                briers[variant] = (mass - truth) ** 2
                entry[f"{variant}_brier"] = float(briers[variant].mean())
            entry["brier_difference"] = block_bootstrap(
                (briers["shared_gamma"] - briers["poisson"]).tolist(),
                [calendar_week(row) for row in subset],
            )
            block["events"][event] = entry
        result[model_id] = block
    return result
