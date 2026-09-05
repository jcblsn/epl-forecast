from dataclasses import dataclass
from datetime import date
from typing import Protocol, Self

import numpy as np

from epl_forecast.schema import Fixture, Match


class ScoreDistribution(Protocol):
    def outcome_probabilities(self) -> tuple[float, float, float]: ...

    def log_probability(self, home_goals: int, away_goals: int) -> float: ...

    def sample(self, rng: np.random.Generator, size: int) -> tuple[np.ndarray, np.ndarray]: ...


@dataclass(frozen=True)
class Forecast:
    probabilities: tuple[float, float, float]
    scores: ScoreDistribution | None = None

    def __post_init__(self) -> None:
        p = np.asarray(self.probabilities)
        if p.shape != (3,) or not np.all(np.isfinite(p)) or np.any(p < 0):
            raise ValueError("Forecast requires three finite, nonnegative H/D/A probabilities")
        if not np.isclose(p.sum(), 1.0, atol=1e-10, rtol=0):
            raise ValueError("Forecast probabilities must sum to one")


class ForecastModel(Protocol):
    as_of: date | None

    def fit(self, matches: list[Match], as_of: date) -> Self: ...

    def predict_match(self, fixture: Fixture) -> Forecast: ...
