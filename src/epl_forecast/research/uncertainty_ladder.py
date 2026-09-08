"""Matched forecast switches; fitted football states remain unchanged."""

from copy import deepcopy

import numpy as np
from scipy.special import ndtr
from scipy.stats import poisson

from epl_forecast.models.base import Forecast
from epl_forecast.models.poisson import IndependentPoisson, PoissonMixture
from epl_forecast.models.quality_tilt_scores import GammaPoissonMixture


def covariance_root(covariance):
    values, vectors = np.linalg.eigh((covariance + covariance.T) / 2)
    if values.min() < -1e-9:
        raise ValueError("Forecast covariance is not positive semidefinite")
    return vectors * np.sqrt(np.maximum(values, 0))


class MatchedStateForecast:
    def __init__(
        self,
        fitted,
        teams,
        season,
        *,
        posterior=True,
        evolution=False,
        innovations=True,
        fixed_teams=(),
        dispersion=None,
    ):
        self.model = fitted.population_snapshot()
        self.model = deepcopy(self.model)
        self.as_of = fitted.as_of
        self.season = season
        for team in sorted(teams):
            self.model._ensure_team(team, season, self.as_of)
        self.team_index = self.model.team_index
        self.mean = self.model.mean.copy()
        self.covariance = (
            self.model.covariance.copy() if posterior else np.zeros_like(self.model.covariance)
        )
        if posterior and fixed_teams:
            indices = [2 + 2 * self.team_index[t] + j for t in sorted(fixed_teams) for j in (0, 1)]
            cross = self.covariance[:, indices]
            self.covariance -= cross @ np.linalg.solve(
                self.covariance[np.ix_(indices, indices)], cross.T
            )
            self.covariance[indices, :] = 0
            self.covariance[:, indices] = 0
        self.evolution, self.innovations, self.dispersion = evolution, innovations, dispersion
        self.posterior = posterior

    def design(self, fixture):
        self.model.validate_fixture(fixture)
        if fixture.season_id != self.season:
            raise ValueError("Matched simulation cannot cross seasons")
        design = np.zeros((2, len(self.mean)))
        design[:, :2] = [[1, 1], [1, 0]]
        for team, transform in zip(
            (fixture.home_team_id, fixture.away_team_id), self.model._team_transforms(), strict=True
        ):
            index = 2 + 2 * self.team_index[team]
            design[:, index : index + 2] = transform
        return design

    def transition(self, years):
        if not self.evolution:
            return np.ones(len(self.mean)), np.zeros(len(self.mean))
        decay, variance = self.model.transition(years, len(self.mean))
        return decay, variance if self.innovations else np.zeros_like(variance)

    def predict_match(self, fixture):
        design = self.design(fixture)
        decay, variance = self.transition((fixture.match_date - self.as_of).days / 365.25)
        mean = self.mean * decay
        covariance = self.covariance * np.outer(decay, decay) + np.diag(variance)
        moments = design @ mean, design @ covariance @ design.T
        scores = (
            PoissonMixture(*moments)
            if self.dispersion is None
            else GammaPoissonMixture(*moments, dispersion=self.dispersion)
        )
        return Forecast(scores.outcome_probabilities(), scores)

    def sample_forecast_state(self, rng, size=1):
        return MatchedPaths(self, rng, size)


class MatchedPaths:
    def __init__(self, forecast, rng, size):
        self.forecast, self.size, self.as_of = forecast, size, forecast.as_of
        self.evolves_future_states = forecast.evolution
        self.day = self.as_of
        self.values = (
            forecast.mean
            + rng.standard_normal((size, len(forecast.mean)))
            @ covariance_root(forecast.covariance).T
        )

    def sample_scores(self, fixture, rng):
        if fixture.match_date < self.day:
            raise ValueError("Matched paths require chronological fixtures")
        design = self.forecast.design(fixture)
        decay, variance = self.forecast.transition((fixture.match_date - self.day).days / 365.25)
        self.values *= decay
        if np.any(variance):
            self.values += rng.standard_normal(self.values.shape) * np.sqrt(variance)
        self.day = fixture.match_date
        rates = np.exp(self.values @ design.T)
        if self.forecast.dispersion is not None:
            shape = self.forecast.dispersion
            rates *= rng.gamma(shape, 1 / shape, self.size)[:, None]
        goals = rng.poisson(rates)
        return goals[:, 0], goals[:, 1]


class M2SeasonDependence:
    """Gaussian copula across fixtures, preserving each independent-Poisson score law.

    Distinct attack and concession factors make the two score uniforms independent
    within each fixture. Reusing team factors creates dependence across fixtures.
    """

    def __init__(self, fitted, teams, dependence):
        if not 0 <= dependence < 1:
            raise ValueError("Season dependence must be in [0, 1)")
        self.model, self.as_of = fitted, fitted.as_of
        self.teams, self.dependence = sorted(teams), dependence
        self.team_index = fitted.team_index

    def predict_match(self, fixture):
        prediction = self.model.predict_match(fixture)
        if not isinstance(prediction.scores, IndependentPoisson):
            raise ValueError("M2 copula requires independent-Poisson match marginals")
        return prediction

    def sample_forecast_state(self, rng, size=1):
        return CopulaPaths(self, rng, size)


class CopulaPaths:
    evolves_future_states = False

    def __init__(self, forecast, rng, size):
        self.forecast, self.size, self.as_of = forecast, size, forecast.as_of
        self.indices = {t: i for i, t in enumerate(forecast.teams)}
        self.factors = rng.standard_normal((size, len(self.indices), 2))

    def sample_scores(self, fixture, rng):
        scores = self.forecast.predict_match(fixture).scores
        h, a = self.indices[fixture.home_team_id], self.indices[fixture.away_team_id]
        shared = np.column_stack(
            (
                self.factors[:, h, 0] + self.factors[:, a, 1],
                self.factors[:, a, 0] + self.factors[:, h, 1],
            )
        ) / np.sqrt(2)
        weight = self.forecast.dependence
        z = np.sqrt(weight) * shared + np.sqrt(1 - weight) * rng.standard_normal((self.size, 2))
        uniforms = np.clip(ndtr(z), np.finfo(float).eps, 1 - np.finfo(float).eps)
        goals = poisson.ppf(uniforms, [scores.home_rate, scores.away_rate]).astype(int)
        return goals[:, 0], goals[:, 1]
