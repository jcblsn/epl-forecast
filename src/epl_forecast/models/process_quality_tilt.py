"""M8 pooled compound-process observation on the frozen centered team dynamics."""

from copy import copy

import numpy as np
from numpy.polynomial.hermite import hermgauss

from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.gaussian import likelihood_laplace_update
from epl_forecast.models.process_observation import ProcessObservation
from epl_forecast.models.process_scores import ProcessScoreMixture
from epl_forecast.models.quality_tilt import (
    BayesianQualityTilt,
    ForwardQualityTiltStates,
    QualityTiltFilter,
)
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter

LOG_SCALE_PRIOR_MEAN = float(np.log(0.25))


class ProcessPopulationFilter(QualityTiltFilter):
    def sample_goal_rates(self, home_rate, away_rate, rng):
        rates = np.column_stack([home_rate, away_rate])
        goals, _ = ProcessObservation([], [], self.process_scale).sample(np.log(rates), rng)
        return goals[:, 0], goals[:, 1]


class ProcessQualityTiltFilter(XGQualityTiltFilter):
    def __init__(self, observations=(), process_scale=0.25, **kwargs):
        ProcessObservation([], [], process_scale)
        self.process_scale = process_scale
        super().__init__(observations=observations, **kwargs)

    def _update(self, design, goals):
        likelihood = ProcessObservation(goals, self._daily_xg, self.process_scale)
        self.mean, self.covariance, evidence = likelihood_laplace_update(
            self.mean, self.covariance, self.observation_design(design), likelihood
        )
        self.log_evidence += evidence

    def fit(self, matches, as_of):
        CenteredQualityTiltFilter.fit(self, matches, as_of)
        self.fit_diagnostics.update(
            {
                "observation_model": "compound Poisson process; downstream Poisson goals",
                "process_scale": self.process_scale,
                "xg_matches": self.xg_updates,
                "xg_availability": "retrospective next-day assumption; late records skipped",
                "equivalence": "frozen centered dynamics; M8 process score marginal",
            }
        )
        return self

    def score_distribution(self, fixture):
        return ProcessScoreMixture(
            *self.forecast_moments(fixture), self.quadrature_order, self.process_scale
        )

    def population_snapshot(self):
        snapshot = ProcessPopulationFilter()
        snapshot.__dict__.update(super().population_snapshot().__dict__)
        return snapshot


class BayesianProcessQualityTilt(BayesianQualityTilt):
    def __init__(
        self,
        observations=(),
        log_scale_mean=LOG_SCALE_PRIOR_MEAN,
        log_scale_sd=0.35,
        scale_order=5,
        quadrature_order=9,
    ):
        if not np.isfinite(log_scale_mean) or not np.isfinite(log_scale_sd) or log_scale_sd <= 0:
            raise ValueError("Log process-scale prior must have finite mean and positive SD")
        if type(scale_order) is not int or scale_order < 2:
            raise ValueError("Process scale quadrature order must be an integer of at least two")
        observations = tuple(observations)
        nodes, masses = hermgauss(scale_order)
        scales = np.exp(log_scale_mean + np.sqrt(2) * log_scale_sd * nodes)
        super().__init__(
            specifications=[dict(XG_DYNAMICS) for _ in scales],
            prior_weights=masses,
            quadrature_order=quadrature_order,
        )
        self.members = [
            ProcessQualityTiltFilter(
                observations, scale, quadrature_order=quadrature_order, **XG_DYNAMICS
            )
            for scale in scales
        ]
        self.specifications = [{**XG_DYNAMICS, "process_scale": float(q)} for q in scales]
        self.scale_prior = {
            "log_mean": float(log_scale_mean),
            "log_sd": log_scale_sd,
            "quadrature_order": scale_order,
        }

    def fit(self, matches, as_of):
        super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "observation_model": "compound Poisson process; downstream goals",
                "xg_matches": self.members[0].xg_updates,
                "process_scale_prior": self.scale_prior,
                "process_scale_uncertainty": "lognormal quadrature; chronological evidence",
                "coordinates": "centered Tilt contrasts and transition-only scoring memory",
            }
        )
        return self

    def sample_forecast_state(self, rng, size=1):
        snapshot = copy(self)
        snapshot.members = [member.population_snapshot() for member in self.members]
        return ForwardQualityTiltStates(snapshot, rng, size)
