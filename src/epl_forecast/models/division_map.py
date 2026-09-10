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
from epl_forecast.models.promotion import PL, TeamPrior
from epl_forecast.models.quality_tilt import AD_FROM_QT, QT_FROM_AD, QualityTiltFilter


class DivisionMap(NamedTuple):
    """Attack and defence compression applied when a club changes division.

    A slope of zero resets an arriving club to what its new division expects of
    it, which is what the operational promotion bridge already does; a slope of
    one carries its whole deviation across, which is what M9 does. Defaults are
    the retained promotion-bridge cohort slopes, measured rather than assumed.

    Both directions compress toward the population they arrive in, so the same
    slopes serve promotion and relegation. Inverting a measured slope would
    amplify instead, and a near-zero slope says the source tells you little about
    the destination either way. No relegation cohort has been measured, so the
    symmetry is an explicit assumption.
    """

    attack_slope: float = 0.539
    defense_slope: float = 0.074

    def validated(self):
        for value in self:
            if not np.isfinite(value) or value < 0:
                raise ValueError("Division map slopes must be finite and nonnegative")
        if max(self) > 1:
            raise ValueError("A division map compresses toward the destination population")
        return self

    @property
    def slopes(self):
        return np.array(self)


CARRIED = DivisionMap(1.0, 1.0)
RESET = DivisionMap(0.0, 0.0)


class DivisionMapPopulation(CrossDivisionQualityTilt):
    """Uncentered coordinates: crossing clubs are compressed toward their new division.

    The map is applied once, when a club's division changes, to its own two state
    slots. Everything the club has learned still crosses with it, so this is a
    compressed carry rather than the reset the promotion bridge performs.
    """

    def __init__(self, division_map=None, map_crossings=True, **kwargs):
        self.division_map = DivisionMap(*(division_map or ())).validated()
        self.map_crossings = bool(map_crossings)
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

    def _population_moments(self):
        """Attack and defence means over the clubs in each division, once per day."""
        if self._division_means is None:
            self._division_means = {}
            for competition in DIVISIONS:
                members = [t for t, d in self.divisions.items() if d == competition]
                if members:
                    states = [AD_FROM_QT @ self.mean[self._team_slice(t)] for t in members]
                    self._division_means[competition] = np.mean(states, axis=0)
        return self._division_means

    def _destination_prior(self, team, season, day, competition):
        """Where the destination division expects an arriving club to sit.

        Promotion has a measured answer already: the retained promotion bridge's
        promoted-club prior, which is what M2, M5 and M7 reset to. That prior is
        measured against a zero-centered Premier League, while this hierarchy's
        club states carry their own floating level, so it is applied as an offset
        from the destination population rather than as an absolute state.
        Relegation has no measured cohort, so the population itself stands in.
        """
        mean = self._population_moments().get(competition)
        if mean is None:
            return None
        if competition == PL:
            prior = QualityTiltFilter._entry_prior(self, team, season, day)
            if prior.source != "league population":
                return (
                    mean + AD_FROM_QT @ prior.mean,
                    AD_FROM_QT @ prior.covariance @ AD_FROM_QT.T,
                )
        return mean, np.eye(2) * self.initial_team_sd**2

    def _map_state(self, team, season, day, competition):
        """Compress a crossing club from its own division toward the one it enters."""
        destination = self._destination_prior(team, season, day, competition)
        source = self._population_moments().get(self.divisions[team])
        if destination is None or source is None:
            return
        anchor, anchor_covariance = destination
        slopes = self.division_map.slopes
        block = self._team_slice(team)
        state = AD_FROM_QT @ self.mean[block]
        covariance = AD_FROM_QT @ self.covariance[block, block] @ AD_FROM_QT.T
        mapped = anchor + slopes * (state - source)
        # Total variance interpolates between carrying the club and resetting it.
        mapped_covariance = (
            np.outer(slopes, slopes) * covariance
            + (1 - np.outer(slopes, slopes)) * anchor_covariance
        )
        transform = QT_FROM_AD @ np.diag(slopes) @ AD_FROM_QT
        self.covariance[block, :] = transform @ self.covariance[block, :]
        self.covariance[:, block] = self.covariance[:, block] @ transform.T
        self.mean[block] = QT_FROM_AD @ mapped
        self.covariance[block, block] = QT_FROM_AD @ mapped_covariance @ QT_FROM_AD.T
        self.crossings.append(
            {
                "team_id": team,
                "season_id": season,
                "to": competition,
                "anchor": anchor.tolist(),
                "carried": state.tolist(),
                "mapped": mapped.tolist(),
            }
        )

    def _ensure_team(self, team, season, day, competition=None):
        crossing = (
            self.map_crossings
            and competition in DIVISIONS
            and team in self.team_index
            and self.divisions.get(team) not in (None, competition)
        )
        if crossing:
            self._map_state(team, season, day, competition)
        super()._ensure_team(team, season, day, competition)
        if crossing:
            block = self._team_slice(team)
            self.entry_priors[team, season] = TeamPrior(
                self.mean[block].copy(),
                self.covariance[block, block].copy(),
                "mapped across divisions",
            )
        if competition in DIVISIONS:
            self.divisions[team] = competition

    def division_summary(self):
        return super().division_summary() | {
            "division_map": self.division_map._asdict() if self.map_crossings else None,
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
