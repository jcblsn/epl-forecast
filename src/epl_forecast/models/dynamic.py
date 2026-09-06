from collections import Counter
from copy import copy
from datetime import date
from itertools import groupby
from typing import Self

import numpy as np

from epl_forecast.models.base import Forecast
from epl_forecast.models.baselines import BaseModel
from epl_forecast.models.gaussian import poisson_laplace_update
from epl_forecast.models.poisson import IndependentPoisson, PoissonMixture
from epl_forecast.models.promotion import (
    CHAMPIONSHIP,
    PL,
    PromotionBridge,
    TeamPrior,
    completed_seasons,
)
from epl_forecast.schema import Fixture, Match


class DynamicAttackDefense(BaseModel):
    def __init__(
        self,
        annual_retention: float = 0.85,
        annual_team_sd: float = 0.18,
        annual_league_sd: float = 0.06,
        initial_team_sd: float = 0.4,
        quadrature_order: int = 9,
        promotion_performance: bool = True,
    ) -> None:
        super().__init__()
        if not np.isfinite(annual_retention) or not 0 < annual_retention <= 1:
            raise ValueError("annual_retention must be in (0, 1]")
        for value in (annual_team_sd, annual_league_sd, initial_team_sd):
            if not np.isfinite(value) or value <= 0:
                raise ValueError("State standard deviations must be finite and positive")
        if type(quadrature_order) is not int or quadrature_order < 2:
            raise ValueError("quadrature_order must be an integer of at least two")
        self.annual_retention = annual_retention
        self.annual_team_sd = annual_team_sd
        self.annual_league_sd = annual_league_sd
        self.initial_team_sd = initial_team_sd
        self.quadrature_order = quadrature_order
        self.promotion_performance = promotion_performance
        self._reset()

    def _reset(self) -> None:
        self.as_of = None
        self._state_date = None
        self._history = []
        self._bridges = {}
        self.team_index = {}
        self._last_season = {}
        self.entry_priors = {}
        self.appearances = Counter()
        self.mean = np.array([np.log(1.2), np.log(1.3)])
        self.covariance = np.diag([0.25**2, 0.25**2])
        self.updates = 0

    def _bridge(self, season: str, as_of: date) -> PromotionBridge:
        available = {
            key: rows
            for key, rows in self._seasons.items()
            if key[1] < season and rows[-1].available_on <= as_of
        }
        key = season, tuple(sorted(available))
        if key not in self._bridges:
            self._bridges[key] = PromotionBridge(
                [m for rows in available.values() for m in rows], as_of, season
            )
        return self._bridges[key]

    def _entry_prior(self, team: str, season: str, as_of: date) -> TeamPrior:
        prior = self._bridge(season, as_of).prior(team, self.promotion_performance)
        if prior is not None:
            return prior
        return TeamPrior(np.zeros(2), np.eye(2) * self.initial_team_sd**2, "league population")

    def _ensure_team(self, team: str, season: str, day: date) -> None:
        if self._last_season.get(team) == season:
            return
        prior = self._entry_prior(team, season, day)
        if team not in self.team_index:
            index = len(self.team_index)
            self.team_index[team] = index
            self.mean = np.r_[self.mean, prior.mean]
            self.covariance = np.pad(self.covariance, ((0, 2), (0, 2)))
            self.covariance[-2:, -2:] = prior.covariance
        elif prior.source == "Championship promotion bridge":
            index = 2 + 2 * self.team_index[team]
            self.mean[index : index + 2] = prior.mean
            self.covariance[index : index + 2, :] = 0
            self.covariance[:, index : index + 2] = 0
            self.covariance[index : index + 2, index : index + 2] = prior.covariance
        else:
            index = 2 + 2 * self.team_index[team]
            prior = TeamPrior(
                self.mean[index : index + 2].copy(),
                self.covariance[index : index + 2, index : index + 2].copy(),
                "previous PL state",
            )
        self.entry_priors[team, season] = prior
        self._last_season[team] = season

    def _advance(self, day: date) -> None:
        if self._state_date is not None:
            years = (day - self._state_date).days / 365.25
            if years < 0:
                raise ValueError("Cannot evolve a state backwards")
            factor = self.annual_retention**years
            team_variance = self.annual_team_sd**2 * (
                years
                if self.annual_retention == 1
                else (1 - factor**2) / (1 - self.annual_retention**2)
            )
            decay = np.r_[np.ones(2), np.full(len(self.mean) - 2, factor)]
            self.mean *= decay
            self.covariance *= np.outer(decay, decay)
            self.covariance += np.diag(
                np.r_[
                    np.full(2, self.annual_league_sd**2 * years),
                    np.full(len(self.mean) - 2, team_variance),
                ]
            )
        self._state_date = day

    def fit(self, matches: list[Match], as_of: date) -> Self:
        if not matches:
            raise ValueError("Training set is empty")
        if any(m.available_on > as_of for m in matches):
            raise ValueError("Training contains a result unavailable at the forecast cutoff")
        if any(m.fixture.competition_id not in {PL, CHAMPIONSHIP} for m in matches):
            raise ValueError("M4 supports PL and Championship evidence")
        if len({m.fixture.match_id for m in matches}) != len(matches):
            raise ValueError("Duplicate training matches")
        ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
        if not any(m.fixture.competition_id == PL for m in ordered):
            raise ValueError("M4 requires Premier League results")
        if (
            self.as_of is None
            or as_of < self.as_of
            or ordered[: len(self._history)] != self._history
        ):
            self._reset()
        new = [m for m in ordered[len(self._history) :] if m.fixture.competition_id == PL]
        self._seasons = completed_seasons(ordered, as_of)
        try:
            for day, games in groupby(new, key=lambda m: m.fixture.match_date):
                games = list(games)
                self._advance(day)
                for match in games:
                    for team in (match.fixture.home_team_id, match.fixture.away_team_id):
                        self._ensure_team(team, match.fixture.season_id, day)
                design = np.zeros((2 * len(games), len(self.mean)))
                goals = []
                for row, match in enumerate(games):
                    h, a = (
                        2 + 2 * self.team_index[t]
                        for t in (match.fixture.home_team_id, match.fixture.away_team_id)
                    )
                    design[2 * row, [0, 1, h, a + 1]] = [1, 1, 1, -1]
                    design[2 * row + 1, [0, a, h + 1]] = [1, 1, -1]
                    goals.extend([match.home_goals, match.away_goals])
                    for team in (match.fixture.home_team_id, match.fixture.away_team_id):
                        self.appearances[team, match.fixture.season_id] += 1
                self.mean, self.covariance = poisson_laplace_update(
                    self.mean, self.covariance, design, np.array(goals)
                )
                self.updates += 1
            self._advance(as_of)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            self._reset()
            raise
        self.as_of, self.competition_id, self._history = as_of, PL, ordered
        self.fit_diagnostics = {
            "inference": "daily joint Laplace Gaussian filter",
            "updates": self.updates,
            "state_dimensions": len(self.mean),
            "training_matches": len(ordered),
            "posterior": "Gaussian conditional on fixed dynamics and empirical Bayes bridge",
        }
        return self

    @property
    def intercept(self):
        return self.mean[0]

    @property
    def home_advantage(self):
        return self.mean[1]

    @property
    def attack(self):
        return self.mean[2::2]

    @property
    def defense(self):
        return self.mean[3::2]

    def _uses_fitted_state(self, team: str, season: str) -> bool:
        return team in self.team_index and (
            self._last_season[team] == season
            or self._bridge(season, self.as_of).prior(team) is None
        )

    def team_state(self, team: str, season: str) -> TeamPrior:
        if self.as_of is None:
            raise ValueError("Fit the model before prediction")
        if self._uses_fitted_state(team, season):
            index = 2 + 2 * self.team_index[team]
            return TeamPrior(
                self.mean[index : index + 2].copy(),
                self.covariance[index : index + 2, index : index + 2].copy(),
                self.entry_priors[team, season].source
                if (team, season) in self.entry_priors
                else "previous PL state",
            )
        return self._entry_prior(team, season, self.as_of)

    def team_summary(self, team: str, season: str) -> dict:
        state = self.team_state(team, season)
        prior = self.entry_priors.get((team, season), state)
        return {
            "team_id": team,
            "attack_log_rate": float(state.mean[0]),
            "defense_log_rate": float(state.mean[1]),
            "attack_sd": float(np.sqrt(state.covariance[0, 0])),
            "defense_sd": float(np.sqrt(state.covariance[1, 1])),
            "attack_defense_covariance": float(state.covariance[0, 1]),
            "state_source": state.source,
            "season_pl_matches": self.appearances[team, season],
            "entry_attack": float(prior.mean[0]),
            "entry_defense": float(prior.mean[1]),
            "entry_attack_sd": float(np.sqrt(prior.covariance[0, 0])),
            "entry_defense_sd": float(np.sqrt(prior.covariance[1, 1])),
        }

    def forecast_moments(self, fixture: Fixture) -> tuple[np.ndarray, np.ndarray]:
        self.validate_fixture(fixture)
        design = np.zeros((2, len(self.mean)))
        design[:, :2] = [[1, 1], [1, 0]]
        extra_mean, extra_covariance = np.zeros(2), np.zeros((2, 2))
        for team, transform in (
            (fixture.home_team_id, np.array([[1, 0], [0, -1]])),
            (fixture.away_team_id, np.array([[0, -1], [1, 0]])),
        ):
            if self._uses_fitted_state(team, fixture.season_id):
                index = 2 + 2 * self.team_index[team]
                design[:, index : index + 2] = transform
            else:
                prior = self.team_state(team, fixture.season_id)
                extra_mean += transform @ prior.mean
                extra_covariance += transform @ prior.covariance @ transform.T
        return (
            design @ self.mean + extra_mean,
            design @ self.covariance @ design.T + extra_covariance,
        )

    def predict_match(self, fixture: Fixture) -> Forecast:
        distribution = PoissonMixture(*self.forecast_moments(fixture), self.quadrature_order)
        return Forecast(distribution.outcome_probabilities(), distribution)

    def sample_forecast_state(self, rng: np.random.Generator, size: int = 1):
        if self.as_of is None:
            raise ValueError("Fit the model before sampling states")
        if type(size) is not int or size < 1:
            raise ValueError("State sample size must be a positive integer")
        snapshot = copy(self)
        snapshot.team_index = self.team_index.copy()
        snapshot._last_season = self._last_season.copy()
        snapshot.entry_priors = self.entry_priors.copy()
        snapshot.mean, snapshot.covariance = self.mean.copy(), self.covariance.copy()
        return SampledTeamStates(snapshot, rng, size)


class SampledTeamStates:
    def __init__(self, model: DynamicAttackDefense, rng: np.random.Generator, size: int):
        self.model, self.size, self.as_of = model, size, model.as_of
        root = np.linalg.cholesky(model.covariance)
        self.values = model.mean + rng.standard_normal((size, len(model.mean))) @ root.T
        self._entry_draws = {}
        self._rng = rng

    def _team(self, team: str, season: str) -> np.ndarray:
        if self.model._uses_fitted_state(team, season):
            index = 2 + 2 * self.model.team_index[team]
            return self.values[:, index : index + 2]
        key = team, season
        if key not in self._entry_draws:
            prior = self.model.team_state(team, season)
            self._entry_draws[key] = (
                prior.mean
                + self._rng.standard_normal((self.size, 2)) @ np.linalg.cholesky(prior.covariance).T
            )
        return self._entry_draws[key]

    def rates(self, fixture: Fixture) -> tuple[np.ndarray, np.ndarray]:
        self.model.validate_fixture(fixture)
        home = self._team(fixture.home_team_id, fixture.season_id)
        away = self._team(fixture.away_team_id, fixture.season_id)
        return (
            np.exp(self.values[:, 0] + self.values[:, 1] + home[:, 0] - away[:, 1]),
            np.exp(self.values[:, 0] + away[:, 0] - home[:, 1]),
        )

    def sample_scores(self, fixture: Fixture, rng: np.random.Generator):
        home, away = self.rates(fixture)
        return rng.poisson(home), rng.poisson(away)

    def predict_match(self, fixture: Fixture) -> Forecast:
        if self.size != 1:
            raise ValueError("Use sample_scores for a batch of forecast states")
        home, away = self.rates(fixture)
        scores = IndependentPoisson(float(home[0]), float(away[0]))
        return Forecast(scores.outcome_probabilities(), scores)
