from collections import defaultdict
from datetime import date
from itertools import groupby
from typing import Self

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit

from epl_forecast.models.base import Forecast
from epl_forecast.models.baselines import BaseModel
from epl_forecast.schema import OUTCOMES, Fixture, Match


def elo_history(
    matches: list[Match], k_factor: float, home_advantage: float
) -> tuple[dict[str, float], np.ndarray, np.ndarray]:
    """Return final ratings and chronological, pre-update differences and outcomes."""
    ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    ratings: dict[str, float] = {}
    differences, outcomes = [], []
    for _, day in groupby(ordered, key=lambda m: m.fixture.match_date):
        updates: dict[str, float] = defaultdict(float)
        for match in day:
            home, away = match.fixture.home_team_id, match.fixture.away_team_id
            difference = ratings.setdefault(home, 0.0) - ratings.setdefault(away, 0.0)
            outcome = OUTCOMES.index(match.outcome)
            differences.append(difference)
            outcomes.append(outcome)
            expected = expit(np.log(10) * (difference + home_advantage) / 400)
            change = k_factor * (1 - outcome / 2 - expected)
            updates[home] += float(change)
            updates[away] -= float(change)
        for team, change in updates.items():
            ratings[team] += change
    return ratings, np.array(differences), np.array(outcomes, dtype=int)


def ordered_log_probabilities(parameters: np.ndarray, differences: np.ndarray) -> np.ndarray:
    intercept, slope, threshold = parameters
    eta = intercept + slope * differences
    # Factoring the sigmoid difference avoids cancellation at large rating gaps.
    draw_log = (
        np.log(-np.expm1(-2 * threshold)) + log_expit(threshold - eta) + log_expit(threshold + eta)
    )
    return np.column_stack((log_expit(eta - threshold), draw_log, log_expit(-eta - threshold)))


def ordered_logit_objective(
    parameters: np.ndarray,
    differences: np.ndarray,
    outcomes: np.ndarray,
    ridge: float,
    prior: np.ndarray,
) -> tuple[float, np.ndarray]:
    log_probabilities = ordered_log_probabilities(parameters, differences)
    eta = parameters[0] + parameters[1] * differences
    threshold = parameters[2]
    home, away = expit(eta - threshold), expit(-eta - threshold)
    home_complement, away_complement = expit(threshold - eta), expit(threshold + eta)
    draw_threshold_gradient = 2 * np.exp(-2 * threshold) / (-np.expm1(-2 * threshold)) + home + away
    eta_gradient = np.column_stack((home_complement, away - home, -away_complement))
    threshold_gradient = np.column_stack(
        (-home_complement, draw_threshold_gradient, -away_complement)
    )
    indices = np.arange(len(outcomes)), outcomes
    residual = -eta_gradient[indices]
    offset = parameters - prior
    objective = -log_probabilities[indices].sum() + 0.5 * ridge * (offset @ offset)
    gradient = np.array(
        [residual.sum(), residual @ differences, -threshold_gradient[indices].sum()]
    )
    return float(objective), gradient + ridge * offset


class EloOrderedLogit(BaseModel):
    def __init__(
        self,
        k_factor: float = 20.0,
        home_advantage: float = 60.0,
        calibration_ridge: float = 1.0,
    ) -> None:
        super().__init__()
        for name, value in (("k_factor", k_factor), ("calibration_ridge", calibration_ridge)):
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not np.isfinite(home_advantage):
            raise ValueError("home_advantage must be finite")
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.calibration_ridge = calibration_ridge

    def fit(self, matches: list[Match], as_of: date) -> Self:
        self.record_fit(matches, as_of)
        ratings, differences, outcomes = elo_history(matches, self.k_factor, self.home_advantage)
        prior = np.array([np.log(10) * self.home_advantage / 400, np.log(10), np.log(5 / 3)])
        result = minimize(
            ordered_logit_objective,
            prior.copy(),
            args=(differences / 400, outcomes, self.calibration_ridge, prior),
            jac=True,
            method="L-BFGS-B",
            bounds=[(None, None), (0.0, None), (1e-6, None)],
            options={"maxiter": 500, "ftol": 1e-11, "gtol": 1e-6},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            self.as_of = None
            raise RuntimeError(f"Ordered-logit optimization failed: {result.message}")
        self.ratings = ratings
        self.coefficients = result.x
        self.fit_diagnostics = {
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "intercept": float(result.x[0]),
            "slope": float(result.x[1]),
            "draw_threshold": float(result.x[2]),
        }
        return self

    def predict_match(self, fixture: Fixture) -> Forecast:
        self.validate_fixture(fixture)
        difference = self.ratings.get(fixture.home_team_id, 0.0) - self.ratings.get(
            fixture.away_team_id, 0.0
        )
        probabilities = np.exp(
            ordered_log_probabilities(self.coefficients, np.array([difference / 400]))[0]
        )
        return Forecast(tuple(float(p) for p in probabilities))
