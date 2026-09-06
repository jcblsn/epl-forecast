"""Centered team Tilt with an explicit, forecast-equivalent scoring transition."""

from copy import copy
from functools import lru_cache

import numpy as np
from scipy.linalg import helmert

from epl_forecast.models.gaussian import score_laplace_update
from epl_forecast.models.promotion import TeamPrior
from epl_forecast.models.quality_tilt import QualityTiltFilter


@lru_cache(maxsize=128)
def tilt_coordinates(teams):
    """Map population coordinates to level, Quality, Tilt contrasts and scoring memory."""
    if type(teams) is not int or teams < 0:
        raise ValueError("Team count must be a nonnegative integer")
    size = 2 + 2 * teams
    transform = np.eye(size)
    if teams:
        indices = np.arange(3, size, 2)
        transform[0, indices] = 2 / teams
        transform[np.ix_(indices, indices)] = np.vstack(
            [helmert(teams), np.full((1, teams), 1 / teams)]
        )
    inverse = np.eye(size)
    if teams:
        inverse[0, -1] = -2
        inverse[np.ix_(indices, indices)] = np.column_stack([helmert(teams).T, np.ones(teams)])
    transform.setflags(write=False)
    inverse.setflags(write=False)
    return transform, inverse


class CenteredQualityTiltFilter(QualityTiltFilter):
    """Infer centered contrasts; the final Tilt slot is temporal scoring memory.

    Memory has no direct coefficient in any observed match rate. Its mean
    reversion drives future scoring level, preserving the original M5 process.
    """

    def __init__(self, independent_poisson=False, **kwargs):
        if independent_poisson:
            kwargs["dispersion"] = None
        super().__init__(**kwargs)

    def _coordinates(self):
        return tilt_coordinates(len(self.team_index))

    def population_moments(self):
        _, inverse = self._coordinates()
        return inverse @ self.mean, inverse @ self.covariance @ inverse.T

    def population_snapshot(self):
        snapshot = QualityTiltFilter()
        snapshot.__dict__.update(self.__dict__)
        snapshot.mean, snapshot.covariance = self.population_moments()
        snapshot.team_index = self.team_index.copy()
        snapshot._last_season = self._last_season.copy()
        snapshot.entry_priors = self.entry_priors.copy()
        return snapshot

    def _ensure_team(self, team, season, day):
        if self._last_season.get(team) == season:
            return
        self.mean, self.covariance = self.population_moments()
        super()._ensure_team(team, season, day)
        transform, _ = self._coordinates()
        self.mean = transform @ self.mean
        self.covariance = transform @ self.covariance @ transform.T

    def transition_matrices(self, years):
        transform, inverse = self._coordinates()
        decay, variance = super().transition(years, len(self.mean))
        return (transform * decay) @ inverse, (transform * variance) @ transform.T

    def _advance(self, day):
        if self._state_date is not None:
            transition, innovation = self.transition_matrices(
                (day - self._state_date).days / 365.25
            )
            self.mean = transition @ self.mean
            self.covariance = transition @ self.covariance @ transition.T + innovation
            self.covariance = (self.covariance + self.covariance.T) / 2
        self._state_date = day

    def observation_design(self, population_design):
        return population_design @ self._coordinates()[1]

    def _update(self, design, goals):
        self.mean, self.covariance, evidence = score_laplace_update(
            self.mean, self.covariance, self.observation_design(design), goals, self.dispersion
        )
        self.log_evidence += evidence

    def fit(self, matches, as_of):
        super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "coordinates": "league scoring level plus orthonormal centered team Tilt contrasts",
                "scoring_memory": "mean-reverting common Tilt; transition-only rate loading",
                "centering_population": list(self.team_index),
                "inference": "daily joint Laplace Gaussian filter in centered coordinates",
                "equivalence": "exact linear transformation of M5 priors, dynamics and likelihood",
            }
        )
        return self

    def _centered_tilt_map(self):
        n = len(self.team_index)
        design = np.zeros((n, len(self.mean)))
        if n > 1:
            design[:, 3:-2:2] = helmert(n).T
        return design

    @property
    def attack(self):
        return self.mean[2::2] + self._centered_tilt_map() @ self.mean

    @property
    def defense(self):
        return self.mean[2::2] - self._centered_tilt_map() @ self.mean

    def team_state(self, team, season):
        if self.as_of is None:
            raise ValueError("Fit the model before prediction")
        if self._uses_fitted_state(team, season):
            index = self.team_index[team]
            design = np.zeros((2, len(self.mean)))
            design[0, 2 + 2 * index] = 1
            design[1] = self._centered_tilt_map()[index]
            source = self.entry_priors.get((team, season))
            return TeamPrior(
                design @ self.mean,
                design @ self.covariance @ design.T,
                source.source if source is not None else "previous PL state",
            )
        prior = self._entry_prior(team, season, self.as_of)
        mean, covariance = prior.mean.copy(), prior.covariance.copy()
        if self.team_index:
            mean[1] -= self.mean[-1]
            covariance[1, 1] += self.covariance[-1, -1]
        return TeamPrior(mean, covariance, prior.source)

    def forecast_moments(self, fixture):
        self.validate_fixture(fixture)
        snapshot = copy(self)
        snapshot.mean, snapshot.covariance = self.mean.copy(), self.covariance.copy()
        snapshot.team_index = self.team_index.copy()
        snapshot._last_season = self._last_season.copy()
        snapshot.entry_priors = self.entry_priors.copy()
        for team in (fixture.home_team_id, fixture.away_team_id):
            snapshot._ensure_team(team, fixture.season_id, self.as_of)
        snapshot._advance(fixture.match_date)
        design = np.zeros((2, len(snapshot.mean)))
        design[:, :2] = [[1, 1], [1, 0]]
        for team, transform in zip(
            (fixture.home_team_id, fixture.away_team_id), self._team_transforms(), strict=True
        ):
            index = 2 + 2 * snapshot.team_index[team]
            design[:, index : index + 2] = transform
        design = snapshot.observation_design(design)
        return design @ snapshot.mean, design @ snapshot.covariance @ design.T

    def sample_forecast_state(self, rng, size=1):
        return self.population_snapshot().sample_forecast_state(rng, size)
