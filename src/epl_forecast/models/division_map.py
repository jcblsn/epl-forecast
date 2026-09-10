"""M10: a division map that compresses club states toward the division population.

M9 carried a club's latent state across divisions unchanged, so the only thing
separating the divisions was an additive scoring level. Its promoted slice failed,
and both the realized promotion slope and a planted-gap regime said why: the
transition is a compression toward the destination population, not a translation.

M10 keeps M9's hierarchy, observations and dynamics and changes exactly two
things. A club that crosses divisions has its state mapped rather than carried,
and the coordinate is centered so the league block owns the population mean of
club Tilt instead of trading against the Championship scoring level.
"""

from typing import NamedTuple

import numpy as np

from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.cross_division import (
    DIVISIONS,
    ChanceObservations,
    CrossDivisionQualityTilt,
)
from epl_forecast.models.promotion import TeamPrior
from epl_forecast.models.quality_tilt import AD_FROM_QT, QT_FROM_AD


class DivisionMap(NamedTuple):
    """Attack and defence compression applied when a club changes division.

    Slopes below one shrink a club toward the destination division's population
    and the residual scales are the spread the mapping cannot predict. Defaults
    are the retained promotion-bridge cohorts, measured rather than assumed.

    Both directions shrink toward the population they arrive in, so the same
    slopes serve promotion and relegation. Inverting a measured slope would
    amplify instead, and a near-zero slope means the source says little about the
    destination in either direction. No relegation cohort has been measured; the
    symmetry is an explicit assumption.
    """

    attack_slope: float = 0.539
    defense_slope: float = 0.074
    attack_residual_sd: float = 0.074
    defense_residual_sd: float = 0.102

    def validated(self):
        for value in self:
            if not np.isfinite(value) or value <= 0:
                raise ValueError("Division map slopes and residual scales must be positive")
        if max(self.attack_slope, self.defense_slope) > 1:
            raise ValueError("A division map compresses toward the destination population")
        return self

    @property
    def slopes(self):
        return np.array([self.attack_slope, self.defense_slope])

    @property
    def residual_variance(self):
        return np.array([self.attack_residual_sd, self.defense_residual_sd]) ** 2


IDENTITY = DivisionMap(1.0, 1.0, 1e-9, 1e-9)


class DivisionMapPopulation(CrossDivisionQualityTilt):
    """Uncentered coordinates: crossing clubs are compressed toward their new division.

    The map is applied once, when a club's division changes, to its own two state
    slots. Everything the club has learned still crosses with it, so this is a
    compressed carry rather than the reset the promotion bridge performs.
    """

    def __init__(self, division_map=None, **kwargs):
        self.division_map = DivisionMap(*(division_map or ())).validated()
        super().__init__(**kwargs)

    def _reset(self):
        super()._reset()
        self.divisions = {}
        self.crossings = []
        self._division_means = None

    def _advance(self, day):
        # One snapshot per day, so clubs crossing together are mapped identically.
        self._division_means = None
        super()._advance(day)

    def _population_attack_defense(self):
        """Attack and defence means over the clubs in each division, once per day."""
        if self._division_means is None:
            self._division_means = {}
            for competition in DIVISIONS:
                members = [t for t, d in self.divisions.items() if d == competition]
                if members:
                    states = [AD_FROM_QT @ self.mean[self._team_slice(t)] for t in members]
                    self._division_means[competition] = np.mean(states, axis=0)
        return self._division_means

    def _map_state(self, team, competition):
        means = self._population_attack_defense()
        source = means.get(self.divisions[team])
        destination = means.get(competition)
        if source is None or destination is None:
            return
        slopes = self.division_map.slopes
        block = self._team_slice(team)
        transform = QT_FROM_AD @ np.diag(slopes) @ AD_FROM_QT
        offset = QT_FROM_AD @ (destination - slopes * source)
        self.mean[block] = transform @ self.mean[block] + offset
        self.covariance[block, :] = transform @ self.covariance[block, :]
        self.covariance[:, block] = self.covariance[:, block] @ transform.T
        self.covariance[block, block] += (
            QT_FROM_AD @ np.diag(self.division_map.residual_variance) @ QT_FROM_AD.T
        )
        self.crossings.append({"team_id": team, "to": competition, "offset": offset.tolist()})

    def _ensure_team(self, team, season, day, competition=None):
        crossing = (
            competition in DIVISIONS
            and team in self.team_index
            and self.divisions.get(team) not in (None, competition)
        )
        if crossing:
            self._map_state(team, competition)
        super()._ensure_team(team, season, day, competition)
        if crossing:
            self.entry_priors[team, season] = TeamPrior(
                self.mean[self._team_slice(team)].copy(),
                self.covariance[self._team_slice(team), self._team_slice(team)].copy(),
                "mapped across divisions",
            )
        if competition in DIVISIONS:
            self.divisions[team] = competition

    def division_summary(self):
        return super().division_summary() | {
            "division_map": self.division_map._asdict(),
            "mapped_crossings": len(self.crossings),
        }


class DivisionMapQualityTilt(CenteredQualityTiltFilter, DivisionMapPopulation):
    """The division map in centered coordinates.

    Club Tilt enters both teams' rates with the same sign, so its population mean
    is a scoring level and trades against the Championship offset. Centering hands
    that mean to the league block, which is what M9's identification audit found
    missing.
    """

    def _population_class(self):
        return DivisionMapPopulation

    def fit(self, matches, as_of):
        super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "division_map": "crossing clubs compressed toward the destination population",
                "map": self.division_map._asdict(),
                "coordinates": "centered club Tilt; the league block owns the scoring level",
            }
        )
        return self


class DivisionMapXG(ChanceObservations, DivisionMapQualityTilt):
    """The division map with team xG on the Premier League side of the hierarchy."""
