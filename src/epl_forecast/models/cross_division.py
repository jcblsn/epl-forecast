"""M9: one club-state hierarchy spanning the Premier League and the Championship.

A club keeps its two-dimensional latent scoring state when it is promoted or
relegated. Division level is a separate slowly changing league quantity, so the
clubs that cross divisions identify a common scale rather than being reset to a
population prior at each entry.
"""

from datetime import date
from itertools import groupby
from types import MappingProxyType

import numpy as np

from epl_forecast.models.gaussian import likelihood_laplace_update
from epl_forecast.models.promotion import CHAMPIONSHIP, PL, TeamPrior
from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.models.xg_observation import ChanceObservation, chance_rows
from epl_forecast.schema import Match

DIVISIONS = (PL, CHAMPIONSHIP)


class CrossDivisionQualityTilt(QualityTiltFilter):
    """Leading block: scoring level, home advantage, division level, division home.

    The Premier League is the reference division, so its offsets are absorbed by
    the shared level and home advantage. Championship offsets are estimated with
    explicit uncertainty and evolve as a slow random walk.
    """

    league_dimensions = 4

    def __init__(
        self,
        division_level_sd=0.30,
        division_home_sd=0.08,
        annual_division_sd=0.03,
        annual_division_home_sd=0.02,
        **kwargs,
    ):
        for value in (
            division_level_sd,
            division_home_sd,
            annual_division_sd,
            annual_division_home_sd,
        ):
            if not np.isfinite(value) or value <= 0:
                raise ValueError("Division prior and innovation scales must be positive")
        self.division_level_sd = division_level_sd
        self.division_home_sd = division_home_sd
        self.annual_division_sd = annual_division_sd
        self.annual_division_home_sd = annual_division_home_sd
        super().__init__(**kwargs)
        self.primary_competition = PL

    def league_prior(self):
        mean, variance = super().league_prior()
        return (
            np.r_[mean, np.zeros(2)],
            np.r_[variance, self.division_level_sd**2, self.division_home_sd**2],
        )

    def league_innovation_sd(self):
        return np.r_[
            super().league_innovation_sd(), self.annual_division_sd, self.annual_division_home_sd
        ]

    def _league_design(self, fixture):
        design = np.zeros((2, self.league_dimensions))
        design[:, :2] = [[1, 1], [1, 0]]
        if fixture.competition_id == CHAMPIONSHIP:
            design[:, 2:] = [[1, 1], [1, 0]]
        return design

    def _entry_prior(self, team, season, as_of):
        """A club is new to the hierarchy once, not once per division."""
        return TeamPrior(
            np.zeros(2), np.eye(2) * self.initial_team_sd**2, "cross-division population"
        )

    def _uses_fitted_state(self, team, season):
        return team in self.team_index

    def _ensure_team(self, team, season, day):
        """A promoted or relegated club carries its state instead of being reset."""
        if self._last_season.get(team) == season:
            return
        if team not in self.team_index:
            prior = self._entry_prior(team, season, day)
            self.team_index[team] = len(self.team_index)
            self.mean = np.r_[self.mean, prior.mean]
            self.covariance = np.pad(self.covariance, ((0, 2), (0, 2)))
            self.covariance[-2:, -2:] = prior.covariance
        else:
            block = self._team_slice(team)
            prior = TeamPrior(
                self.mean[block].copy(),
                self.covariance[block, block].copy(),
                "carried across seasons and divisions",
            )
        self.entry_priors[team, season] = prior
        self._last_season[team] = season

    def validate_fixture(self, fixture):
        if self.as_of is None:
            raise ValueError("Fit the model before prediction")
        if fixture.match_date < self.as_of:
            raise ValueError("Fixture predates the model's training cutoff")
        if fixture.competition_id not in DIVISIONS:
            raise ValueError("M9 forecasts the Premier League and the Championship only")

    def fit(self, matches: list[Match], as_of: date):
        if not matches:
            raise ValueError("Training set is empty")
        if any(m.available_on > as_of for m in matches):
            raise ValueError("Training contains a result unavailable at the forecast cutoff")
        if any(m.fixture.competition_id not in DIVISIONS for m in matches):
            raise ValueError("M9 supports PL and Championship evidence")
        if len({m.fixture.match_id for m in matches}) != len(matches):
            raise ValueError("Duplicate training matches")
        ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
        if (
            self.as_of is None
            or as_of < self.as_of
            or ordered[: len(self._history)] != self._history
        ):
            self._reset()
        new = ordered[len(self._history) :]
        try:
            for day, games in groupby(new, key=lambda m: m.fixture.match_date):
                games = list(games)
                self._advance(day)
                for match in games:
                    for team in (match.fixture.home_team_id, match.fixture.away_team_id):
                        self._ensure_team(team, match.fixture.season_id, day)
                self._prepare_observations(games)
                design = np.zeros((2 * len(games), len(self.mean)))
                goals = []
                for row, match in enumerate(games):
                    block = design[2 * row : 2 * row + 2]
                    block[:, : self.league_dimensions] = self._league_design(match.fixture)
                    home_transform, away_transform = self._team_transforms()
                    block[:, self._team_slice(match.fixture.home_team_id)] = home_transform
                    block[:, self._team_slice(match.fixture.away_team_id)] = away_transform
                    self._augment_design(block, match)
                    goals.extend([match.home_goals, match.away_goals])
                    self.appearances[match.fixture.home_team_id, match.fixture.season_id] += 1
                    self.appearances[match.fixture.away_team_id, match.fixture.season_id] += 1
                self._update(design, np.array(goals))
                self.updates += 1
            self._advance(as_of)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            self._reset()
            raise
        self.as_of, self._history = as_of, ordered
        self.competition_id = PL
        self.fit_diagnostics = {
            "inference": "daily joint Laplace Gaussian filter over both divisions",
            "updates": self.updates,
            "state_dimensions": len(self.mean),
            "training_matches": len(ordered),
            "clubs": len(self.team_index),
            "coordinates": "shared level, home advantage, Championship level and home offsets",
            "entry": "population prior once per club; states carried across divisions",
            "posterior": "Gaussian conditional on fixed dynamics",
        }
        return self

    @property
    def division_level(self):
        return self.mean[2]

    @property
    def division_home_advantage(self):
        return self.mean[3]

    def division_summary(self):
        return {
            "intercept": float(self.mean[0]),
            "home_advantage": float(self.mean[1]),
            "championship_level": float(self.mean[2]),
            "championship_home_offset": float(self.mean[3]),
            "championship_level_sd": float(np.sqrt(self.covariance[2, 2])),
            "championship_home_offset_sd": float(np.sqrt(self.covariance[3, 3])),
            "home_advantage_sd": float(np.sqrt(self.covariance[1, 1])),
            "clubs": len(self.team_index),
            "crossed_divisions": sorted(self._crossed()),
        }

    def _crossed(self):
        seen = {}
        crossed = set()
        for match in self._history:
            for team in (match.fixture.home_team_id, match.fixture.away_team_id):
                if (
                    seen.setdefault(team, match.fixture.competition_id)
                    != match.fixture.competition_id
                ):
                    crossed.add(team)
        return crossed


class CrossDivisionXG(CrossDivisionQualityTilt):
    """The same club states, with team xG as a noisy measurement of the process.

    Goals stay the Binomial thinning of a Poisson opportunity process and xG its
    Gamma measurement, so xG never double-counts goals and is never forced to
    equal an additive player total.
    """

    def __init__(self, observations=(), chance_probability=0.2, **kwargs):
        if kwargs.get("dispersion") is not None:
            raise ValueError("Opportunity thinning implies marginal independent Poisson goals")
        kwargs["dispersion"] = None
        self.chance_probability = chance_probability
        ChanceObservation([], [], chance_probability)
        self._observations = chance_rows(observations)
        super().__init__(**kwargs)

    @property
    def observations(self):
        return MappingProxyType(self._observations)

    def _reset(self):
        super()._reset()
        self.xg_updates = 0
        self._daily_xg = np.empty(0)

    def _prepare_observations(self, games):
        values = []
        for match in games:
            row = self.observations.get(match.fixture.match_id)
            if row is not None:
                day, available, home, away, home_xg, away_xg = row
                if day != match.fixture.match_date or (home, away) != (
                    match.home_goals,
                    match.away_goals,
                ):
                    raise ValueError("xG does not reconcile with training result")
                # Daily filtering cannot retrofit observations published after this update.
                if available <= match.available_on:
                    values.extend([home_xg, away_xg])
                    self.xg_updates += 1
                    continue
            values.extend([np.nan, np.nan])
        self._daily_xg = np.asarray(values)

    def _update(self, design, goals):
        likelihood = ChanceObservation(goals, self._daily_xg, self.chance_probability)
        self.mean, self.covariance, evidence = likelihood_laplace_update(
            self.mean, self.covariance, design, likelihood
        )
        self.log_evidence += evidence

    def fit(self, matches, as_of):
        super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "observation_model": "Poisson opportunities; Gamma xG; Binomial goals",
                "chance_probability": self.chance_probability,
                "xg_matches": self.xg_updates,
                "xg_availability": "retrospective next-day assumption; late records skipped",
            }
        )
        return self
