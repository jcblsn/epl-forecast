from dataclasses import dataclass

import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import logsumexp
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


class PoissonMixture:
    """Gaussian quadrature over joint log rates, conditional independent Poisson goals."""

    def __init__(self, log_mean: np.ndarray, log_covariance: np.ndarray, order: int = 9):
        if type(order) is not int or order < 2:
            raise ValueError("Quadrature order must be an integer of at least two")
        mean, covariance = np.asarray(log_mean), np.asarray(log_covariance)
        if mean.shape != (2,) or covariance.shape != (2, 2):
            raise ValueError("Joint log rates need a two-dimensional Gaussian")
        if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(covariance)):
            raise ValueError("Log-rate moments must be finite")
        if not np.allclose(covariance, covariance.T, atol=1e-12):
            raise ValueError("Log-rate covariance must be symmetric")
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        if eigenvalues.min() < -1e-10:
            raise ValueError("Log-rate covariance must be positive semidefinite")
        self.log_mean, self.log_covariance = mean.copy(), covariance.copy()
        root = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0))
        nodes, weights = hermgauss(order)
        z = np.array(np.meshgrid(nodes, nodes, indexing="ij")).reshape(2, -1).T * np.sqrt(2)
        rates = np.exp(mean + z @ root.T)
        self.home_rates, self.away_rates = rates.T
        self.weights = np.outer(weights, weights).ravel() / np.pi
        self.weights /= self.weights.sum()
        self.home_rate = float(self.weights @ self.home_rates)
        self.away_rate = float(self.weights @ self.away_rates)

    def outcome_probabilities(self) -> tuple[float, float, float]:
        h, a = self.home_rates, self.away_rates
        return (
            float(self.weights @ skellam.sf(0, h, a)),
            float(self.weights @ skellam.pmf(0, h, a)),
            float(self.weights @ skellam.cdf(-1, h, a)),
        )

    def log_probability(self, home_goals: int, away_goals: int) -> float:
        return float(
            logsumexp(
                np.log(self.weights)
                + poisson.logpmf(home_goals, self.home_rates)
                + poisson.logpmf(away_goals, self.away_rates)
            )
        )

    def grid(self, max_goals: int = 10) -> tuple[np.ndarray, float]:
        if type(max_goals) is not int or max_goals < 0:
            raise ValueError("max_goals must be a nonnegative integer")
        goals = np.arange(max_goals + 1)
        home = poisson.pmf(goals[None, :], self.home_rates[:, None])
        away = poisson.pmf(goals[None, :], self.away_rates[:, None])
        grid = (home.T * self.weights) @ away
        return grid, max(0.0, 1.0 - float(grid.sum()))

    def sample(self, rng: np.random.Generator, size: int) -> tuple[np.ndarray, np.ndarray]:
        component = rng.choice(len(self.weights), size=size, p=self.weights)
        return rng.poisson(self.home_rates[component]), rng.poisson(self.away_rates[component])
