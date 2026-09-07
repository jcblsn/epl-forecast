"""M8 compound-Poisson process mass followed by conditional Poisson scoring."""

import numpy as np
from scipy.special import gammaln, logsumexp, xlogy


class ProcessObservation:
    def __init__(self, goals, xg, process_scale):
        self.goals = np.asarray(goals, dtype=float)
        self.xg = np.asarray(xg, dtype=float)
        if not np.isfinite(process_scale) or process_scale <= 0:
            raise ValueError("Process scale must be finite and positive")
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
            raise ValueError("Positive goals with zero xG are outside the process model")
        self.scale = float(process_scale)

    def __call__(self, eta):
        eta = np.asarray(eta, dtype=float)
        if eta.shape != self.goals.shape:
            raise ValueError("Log rates must match observation shape")
        rates = np.exp(eta)
        if not np.isfinite(rates).all():
            return -np.inf, np.zeros(len(eta)), np.eye(len(eta))
        q = self.scale
        logp, gradient, curvature = 0.0, np.empty(len(eta)), np.empty(len(eta))
        for i, (g, x, r) in enumerate(zip(self.goals, self.xg, rates, strict=True)):
            intensity = r / q
            if x == 0:
                logp -= intensity
                gradient[i], curvature[i] = -intensity, intensity
                continue
            if np.isnan(x) and g == 0:
                zero_rate = r / (1 + q)
                logp -= zero_rate
                gradient[i], curvature[i] = -zero_rate, zero_rate
                continue
            count = 128
            while True:
                n = np.arange(1, count + 1, dtype=float)
                values = n * (eta[i] - np.log(q)) - gammaln(n + 1)
                if np.isnan(x):
                    values += (
                        gammaln(n + g)
                        - gammaln(n)
                        - gammaln(g + 1)
                        + g * np.log(q)
                        - (n + g) * np.log1p(q)
                    )
                    ratio = intensity * (count + g) / (count * (count + 1) * (1 + q))
                else:
                    values += (
                        (n - 1) * np.log(x)
                        - x / q
                        - gammaln(n)
                        - n * np.log(q)
                        + xlogy(g, x)
                        - x
                        - gammaln(g + 1)
                    )
                    ratio = intensity * x / (q * count * (count + 1))
                normalizer = logsumexp(values)
                weights = np.exp(values - normalizer)
                if ratio < 1 and weights[-1] * ratio / (1 - ratio) < 1e-14:
                    break
                if count >= 16384:
                    raise RuntimeError("Process likelihood series failed to converge")
                count *= 2
            expected = weights @ n
            variance = weights @ (n - expected) ** 2
            logp += normalizer - intensity
            gradient[i], curvature[i] = expected - intensity, intensity - variance
        return float(logp), gradient, np.diag(curvature)

    def sample(self, log_rates, rng):
        packets = rng.poisson(np.exp(log_rates) / self.scale)
        xg = rng.gamma(packets, self.scale)
        return rng.poisson(xg), xg
