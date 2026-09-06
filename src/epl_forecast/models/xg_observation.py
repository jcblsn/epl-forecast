"""Joint goals/xG likelihood from a thinned Poisson opportunity process."""

import numpy as np
from scipy.special import gammaln, logsumexp


class ChanceObservation:
    def __init__(self, goals, xg, chance_probability):
        self.goals, self.xg = np.asarray(goals), np.asarray(xg, dtype=float)
        p = chance_probability
        if not np.isfinite(p) or not 0 < p < 1:
            raise ValueError("Chance probability must be in (0, 1)")
        if self.goals.ndim != 1 or self.xg.shape != self.goals.shape:
            raise ValueError("Goals and xG must be matching vectors")
        if (
            not np.isfinite(self.goals).all()
            or np.any(self.goals < 0)
            or np.any(self.goals != np.floor(self.goals))
        ):
            raise ValueError("Goals must be nonnegative integers")
        if np.any(np.isinf(self.xg)) or np.any(self.xg < 0):
            raise ValueError("xG must be nonnegative and finite, or NaN for missing")
        if np.any((self.xg == 0) & (self.goals > 0)):
            raise ValueError("Positive goals with zero xG are outside the opportunity model")
        self.p = p
        self.terms = [
            self._terms(g, x, 128) if x > 0 else None
            for g, x in zip(self.goals, self.xg, strict=True)
        ]

    def _terms(self, goals, xg, count):
        missed = np.arange(0 if goals else 1, count, dtype=float)
        total = goals + missed
        constant = (
            -gammaln(goals + 1)
            - gammaln(missed + 1)
            - gammaln(total)
            + missed * np.log((1 - self.p) / self.p)
            + (total - 1) * np.log(xg)
            - total * np.log(self.p)
            - xg / self.p
        )
        return missed, total, constant

    def __call__(self, eta):
        rates = np.exp(eta)
        if not np.isfinite(rates).all():
            return -np.inf, np.zeros(len(eta)), np.eye(len(eta))
        logp, score, curvature = 0.0, np.empty(len(eta)), np.empty(len(eta))
        for i, (g, x, rate) in enumerate(zip(self.goals, self.xg, rates, strict=True)):
            if np.isnan(x):
                logp += g * eta[i] - rate - gammaln(g + 1)
                score[i], curvature[i] = g - rate, rate
            elif x == 0:
                logp -= rate / self.p
                score[i], curvature[i] = -rate / self.p, rate / self.p
            else:
                terms = self.terms[i]
                while True:
                    missed, total, constant = terms
                    values = total * eta[i] + constant
                    normalizer = logsumexp(values)
                    weights = np.exp(values - normalizer)
                    ratio = rate * (1 - self.p) * x / self.p**2 / ((missed[-1] + 1) * total[-1])
                    if ratio < 1 and weights[-1] * ratio / (1 - ratio) < 1e-14:
                        break
                    if len(missed) >= 8191:
                        raise RuntimeError("Opportunity likelihood series failed to converge")
                    terms = self._terms(g, x, 2 * (int(missed[-1]) + 1))
                expected = weights @ missed
                variance = weights @ (missed - expected) ** 2
                logp += normalizer - rate / self.p
                score[i], curvature[i] = g + expected - rate / self.p, rate / self.p - variance
        return float(logp), score, np.diag(curvature)

    def sample(self, log_rates, rng):
        opportunities = rng.poisson(np.exp(log_rates) / self.p)
        goals = rng.binomial(opportunities, self.p)
        xg = rng.gamma(opportunities, self.p)
        return goals, xg
