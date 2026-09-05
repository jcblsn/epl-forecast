from datetime import date
from typing import Self

import numpy as np
from scipy.optimize import minimize

from epl_forecast.models.base import Forecast
from epl_forecast.models.poisson import IndependentPoisson
from epl_forecast.schema import OUTCOMES, Fixture, Match, validate_training


def time_weights(matches: list[Match], as_of: date, half_life_days: float | None) -> np.ndarray:
    if half_life_days is None:
        return np.ones(len(matches))
    if not np.isfinite(half_life_days) or half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    ages = np.array([(as_of - match.fixture.match_date).days for match in matches])
    return np.exp2(-ages / half_life_days)


class BaseModel:
    def __init__(self) -> None:
        self.as_of: date | None = None
        self.competition_id: str | None = None

    def record_fit(self, matches: list[Match], as_of: date) -> None:
        validate_training(matches, as_of)
        self.as_of = as_of
        self.competition_id = matches[0].fixture.competition_id

    def validate_fixture(self, fixture: Fixture) -> None:
        if self.as_of is None:
            raise ValueError("Fit the model before prediction")
        if fixture.match_date < self.as_of:
            raise ValueError("Fixture predates the model's training cutoff")
        if fixture.competition_id != self.competition_id:
            raise ValueError("Fixture competition differs from model training")


class LeagueFrequency(BaseModel):
    def __init__(self, alpha: float = 1.0) -> None:
        super().__init__()
        if not np.isfinite(alpha) or alpha <= 0:
            raise ValueError("alpha must be positive")
        self.alpha = alpha

    def fit(self, matches: list[Match], as_of: date) -> Self:
        self.record_fit(matches, as_of)
        counts = np.array([sum(m.outcome == outcome for m in matches) for outcome in OUTCOMES])
        self.probabilities = tuple((counts + self.alpha) / (len(matches) + 3 * self.alpha))
        return self

    def predict_match(self, fixture: Fixture) -> Forecast:
        self.validate_fixture(fixture)
        return Forecast(self.probabilities)


class LeaguePoisson(BaseModel):
    def __init__(self, half_life_days: float | None = 365.0) -> None:
        super().__init__()
        self.half_life_days = half_life_days

    def fit(self, matches: list[Match], as_of: date) -> Self:
        self.record_fit(matches, as_of)
        weights = time_weights(matches, as_of, self.half_life_days)
        home = np.array([match.home_goals for match in matches])
        away = np.array([match.away_goals for match in matches])
        self.distribution = IndependentPoisson(
            float((weights @ home + 1) / (weights.sum() + 1)),
            float((weights @ away + 1) / (weights.sum() + 1)),
        )
        return self

    def predict_match(self, fixture: Fixture) -> Forecast:
        self.validate_fixture(fixture)
        return Forecast(self.distribution.outcome_probabilities(), self.distribution)


def poisson_objective(
    parameters: np.ndarray,
    home: np.ndarray,
    away: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    ridge: float,
) -> tuple[float, np.ndarray]:
    n = (len(parameters) - 2) // 2
    attack_raw, defense_raw = parameters[2 : 2 + n], parameters[2 + n :]
    attack, defense = attack_raw - attack_raw.mean(), defense_raw - defense_raw.mean()
    eta_home = parameters[0] + parameters[1] + attack[home] - defense[away]
    eta_away = parameters[0] + attack[away] - defense[home]
    mu_home, mu_away = np.exp(eta_home), np.exp(eta_away)
    objective = np.sum(
        weights * (mu_home - home_goals * eta_home + mu_away - away_goals * eta_away)
    )
    objective += 0.5 * ridge * np.sum(parameters[2:] ** 2)
    residual_home = weights * (mu_home - home_goals)
    residual_away = weights * (mu_away - away_goals)
    gradient = np.zeros_like(parameters)
    gradient[0] = residual_home.sum() + residual_away.sum()
    gradient[1] = residual_home.sum()
    grad_attack = np.bincount(home, residual_home, minlength=n) + np.bincount(
        away, residual_away, minlength=n
    )
    grad_defense = -np.bincount(away, residual_home, minlength=n) - np.bincount(
        home, residual_away, minlength=n
    )
    gradient[2 : 2 + n] = grad_attack - grad_attack.mean() + ridge * attack_raw
    gradient[2 + n :] = grad_defense - grad_defense.mean() + ridge * defense_raw
    # One virtual 1-1 match keeps global rates finite even for all-zero training scores.
    base_home, base_away = np.exp(parameters[0] + parameters[1]), np.exp(parameters[0])
    objective += base_home + base_away - 2 * parameters[0] - parameters[1]
    gradient[0] += base_home + base_away - 2
    gradient[1] += base_home - 1
    return float(objective), gradient


class AttackDefensePoisson(BaseModel):
    def __init__(self, ridge: float = 5.0, half_life_days: float | None = 365.0) -> None:
        super().__init__()
        if not np.isfinite(ridge) or ridge <= 0:
            raise ValueError("ridge must be positive")
        self.ridge = ridge
        self.half_life_days = half_life_days

    def fit(self, matches: list[Match], as_of: date) -> Self:
        self.record_fit(matches, as_of)
        teams = sorted(
            {
                team
                for match in matches
                for team in (match.fixture.home_team_id, match.fixture.away_team_id)
            }
        )
        self.team_index = {team: index for index, team in enumerate(teams)}
        home = np.array([self.team_index[m.fixture.home_team_id] for m in matches])
        away = np.array([self.team_index[m.fixture.away_team_id] for m in matches])
        home_goals = np.array([m.home_goals for m in matches])
        away_goals = np.array([m.away_goals for m in matches])
        weights = time_weights(matches, as_of, self.half_life_days)
        home_rate = (weights @ home_goals + 1) / (weights.sum() + 1)
        away_rate = (weights @ away_goals + 1) / (weights.sum() + 1)
        initial = np.zeros(2 + 2 * len(teams))
        initial[:2] = np.log(away_rate), np.log(home_rate / away_rate)
        result = minimize(
            poisson_objective,
            initial,
            args=(home, away, home_goals, away_goals, weights, self.ridge),
            jac=True,
            method="L-BFGS-B",
            options={"maxiter": 500, "ftol": 1e-11, "gtol": 1e-6},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            self.as_of = None
            raise RuntimeError(f"Poisson optimization failed: {result.message}")
        self.intercept, self.home_advantage = result.x[:2]
        self.attack = result.x[2 : 2 + len(teams)]
        self.defense = result.x[2 + len(teams) :]
        self.attack -= self.attack.mean()
        self.defense -= self.defense.mean()
        self.fit_diagnostics = {"iterations": int(result.nit), "objective": float(result.fun)}
        return self

    def predict_match(self, fixture: Fixture) -> Forecast:
        self.validate_fixture(fixture)
        home = self.team_index.get(fixture.home_team_id)
        away = self.team_index.get(fixture.away_team_id)
        home_attack = self.attack[home] if home is not None else 0.0
        away_attack = self.attack[away] if away is not None else 0.0
        home_defense = self.defense[home] if home is not None else 0.0
        away_defense = self.defense[away] if away is not None else 0.0
        distribution = IndependentPoisson(
            float(np.exp(self.intercept + self.home_advantage + home_attack - away_defense)),
            float(np.exp(self.intercept + away_attack - home_defense)),
        )
        return Forecast(distribution.outcome_probabilities(), distribution)
