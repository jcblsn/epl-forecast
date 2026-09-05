from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson, skellam


@dataclass(frozen=True)
class IndependentPoisson:
    home_rate: float
    away_rate: float

    def __post_init__(self) -> None:
        if any(not np.isfinite(rate) or rate <= 0 for rate in (self.home_rate, self.away_rate)):
            raise ValueError("Poisson rates must be finite and positive")

    def outcome_probabilities(self) -> tuple[float, float, float]:
        home = float(skellam.sf(0, self.home_rate, self.away_rate))
        draw = float(skellam.pmf(0, self.home_rate, self.away_rate))
        away = float(skellam.cdf(-1, self.home_rate, self.away_rate))
        return home, draw, away

    def log_probability(self, home_goals: int, away_goals: int) -> float:
        return float(
            poisson.logpmf(home_goals, self.home_rate) + poisson.logpmf(away_goals, self.away_rate)
        )

    def grid(self, max_goals: int = 10) -> tuple[np.ndarray, float]:
        if type(max_goals) is not int or max_goals < 0:
            raise ValueError("max_goals must be a nonnegative integer")
        goals = np.arange(max_goals + 1)
        probabilities = np.outer(
            poisson.pmf(goals, self.home_rate), poisson.pmf(goals, self.away_rate)
        )
        return probabilities, max(0.0, 1.0 - float(probabilities.sum()))

    def sample(self, rng: np.random.Generator, size: int) -> tuple[np.ndarray, np.ndarray]:
        return rng.poisson(self.home_rate, size), rng.poisson(self.away_rate, size)
