"""M8 compound-Poisson process mass followed by conditional Poisson scoring."""

import numpy as np
from scipy.special import gammaln, ive, logsumexp, xlogy


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
            if np.isnan(x):
                # Nonzero scoring packets form a thinned Poisson process with geometric jumps.
                n = np.arange(1, int(g) + 1, dtype=float)
                intensity = r / (1 + q)
                values = (
                    n * (eta[i] - np.log1p(q))
                    - gammaln(n + 1)
                    + gammaln(g)
                    - gammaln(n)
                    - gammaln(g - n + 1)
                    - n * np.log1p(q)
                    + (g - n) * (np.log(q) - np.log1p(q))
                )
                normalizer = logsumexp(values)
                weights = np.exp(values - normalizer)
                expected = weights @ n
                variance = weights @ (n - expected) ** 2
                logp += normalizer - intensity
            else:
                z = 2 * np.sqrt(r) * np.sqrt(x) / q
                bessel = ive(1, z)
                if z > 1e6:
                    expected, variance = z / 2 + 0.25, z / 4
                    log_bessel = -0.5 * np.log(2 * np.pi * z) - 3 / (8 * z)
                elif z < 1e-5:
                    u = r * x / q**2
                    expected, variance = 1 + u / 2, u / 2
                    log_bessel = np.log(z / 2) + np.log1p(u / 2) - z
                else:
                    expected = z / 2 * ive(0, z) / bessel
                    variance = z**2 / 4 + expected - expected**2
                    log_bessel = np.log(bessel)
                logp += (
                    -intensity
                    - x / q
                    + z
                    + log_bessel
                    + 0.5 * (eta[i] - np.log(x))
                    - np.log(q)
                    + xlogy(g, x)
                    - x
                    - gammaln(g + 1)
                )
            gradient[i], curvature[i] = expected - intensity, intensity - variance
        return float(logp), gradient, np.diag(curvature)

    def sample(self, log_rates, rng):
        packets = rng.poisson(np.exp(log_rates) / self.scale)
        xg = rng.gamma(packets, self.scale)
        return rng.poisson(xg), xg
