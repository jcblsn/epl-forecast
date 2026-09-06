"""Bounded integration diagnostics; no change to production inference or weights."""

import numpy as np
from scipy.special import gammaln, logsumexp, ndtri
from scipy.stats import qmc

from epl_forecast.models.gaussian import score_laplace_update
from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.models.quality_tilt_scores import joint_logpmf


def importance_update(mean, covariance, design, goals, dispersion, seed, power=12):
    """Integrate in the likelihood's Gaussian subspace using a Laplace proposal."""
    posterior_mean, posterior_covariance, laplace = score_laplace_update(
        mean, covariance, design, goals, dispersion
    )
    cross = covariance @ design.T
    values, vectors = np.linalg.eigh(design @ cross)
    keep = values > 1e-12
    root = vectors[:, keep] * np.sqrt(values[keep])
    inverse = (vectors[:, keep] / np.sqrt(values[keep])).T
    location = design @ mean
    proposal_mean = inverse @ (design @ posterior_mean - location)
    proposal_covariance = inverse @ design @ posterior_covariance @ design.T @ inverse.T
    proposal_root = np.linalg.cholesky(proposal_covariance)
    uniform = qmc.Sobol(len(proposal_mean), scramble=True, seed=seed).random_base2(power)
    z = ndtri(np.clip(uniform, 1e-12, 1 - 1e-12))
    values = proposal_mean + z @ proposal_root.T
    eta = location + values @ root.T
    rates = np.exp(eta)
    if dispersion is None:
        likelihood = np.sum(goals * eta - rates - gammaln(goals + 1), axis=1)
    else:
        likelihood = joint_logpmf(
            goals[::2], goals[1::2], rates[:, ::2], rates[:, 1::2], dispersion
        ).sum(axis=1)
    log_weights = (
        likelihood
        + 0.5 * (np.sum(z**2, axis=1) - np.sum(values**2, axis=1))
        + np.log(np.diag(proposal_root)).sum()
    )
    evidence = logsumexp(log_weights) - np.log(len(values))
    weights = np.exp(log_weights - logsumexp(log_weights))
    projected_mean = weights @ values
    deviations = values - projected_mean
    projected_covariance = (deviations.T * weights) @ deviations
    mapping = cross @ inverse.T
    corrected_covariance = (
        covariance + mapping @ (projected_covariance - np.eye(len(projected_mean))) @ mapping.T
    )
    return (
        mean + mapping @ projected_mean,
        (corrected_covariance + corrected_covariance.T) / 2,
        {
            "laplace": laplace,
            "importance": float(evidence),
            "correction": float(evidence - laplace),
            "ess_fraction": float(1 / (weights @ weights) / len(weights)),
        },
    )


class EvidenceCheckedFilter(QualityTiltFilter):
    def __init__(self, *, seed=20260906, power=12, correct_moments=False, **kwargs):
        self.seed, self.power, self.correct_moments = seed, power, correct_moments
        super().__init__(**kwargs)

    def _reset(self):
        super()._reset()
        self.integration_checks = []

    def _update(self, design, goals):
        mean, covariance, check = importance_update(
            self.mean,
            self.covariance,
            design,
            goals,
            self.dispersion,
            self.seed + len(self.integration_checks),
            self.power,
        )
        self.integration_checks.append({"date": str(self._state_date), **check})
        if self.correct_moments:
            self.mean, self.covariance = mean, covariance
            self.log_evidence += check["importance"]
        else:
            super()._update(design, goals)


def relevant_functionals(data):
    dimension = data["design"].shape[-1]
    league = np.eye(dimension)[0]
    common_tilt = np.zeros(dimension)
    common_tilt[3::2] = 1 / len(data["teams"])
    return np.vstack(
        [
            league,
            common_tilt,
            league + 2 * common_tilt,
            data["design"].reshape(-1, dimension),
        ]
    )
