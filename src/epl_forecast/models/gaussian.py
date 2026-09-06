import numpy as np
from scipy.linalg import cho_factor, cho_solve


def poisson_laplace_update(
    mean: np.ndarray, covariance: np.ndarray, design: np.ndarray, goals: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """One joint Poisson update of a Gaussian prior; retain all state covariances."""
    cross = covariance @ design.T
    projected = design @ cross
    values, vectors = np.linalg.eigh(projected)
    keep = values > 1e-12
    root = vectors[:, keep] * np.sqrt(values[keep])
    location = design @ mean
    mode = np.zeros(root.shape[1])

    def objective(u):
        eta = location + root @ u
        with np.errstate(over="ignore"):
            return 0.5 * (u @ u) + np.sum(np.exp(eta) - goals * eta)

    for _ in range(50):
        rates = np.exp(location + root @ mode)
        gradient = mode + root.T @ (rates - goals)
        hessian = np.eye(len(mode)) + (root.T * rates) @ root
        step = cho_solve(cho_factor(hessian), gradient)
        if np.max(np.abs(gradient), initial=0) < 1e-8:
            break
        scale, old = 1.0, objective(mode)
        while objective(mode - scale * step) > old - 1e-4 * scale * (gradient @ step):
            scale *= 0.5
            if scale < 1e-10:
                if np.max(np.abs(step), initial=0) < 1e-7:
                    break
                raise RuntimeError("Poisson Laplace line search failed")
        mode -= scale * step
        if np.max(np.abs(scale * step), initial=0) < 1e-9:
            break
    else:
        raise RuntimeError("Poisson Laplace update did not converge")
    rates = np.exp(location + root @ mode)
    updated_mean = mean + cross @ (goals - rates)
    precision_factor = cho_factor(projected + np.diag(1 / rates))
    updated_covariance = covariance - cross @ cho_solve(precision_factor, cross.T)
    return updated_mean, (updated_covariance + updated_covariance.T) / 2


def score_laplace_update(mean, covariance, design, goals, dispersion=None):
    """Daily joint Laplace update and approximate predictive log evidence."""
    from scipy.special import gammaln, logsumexp

    from epl_forecast.models.quality_tilt_scores import joint_logpmf

    cross = covariance @ design.T
    projected = design @ cross
    values, vectors = np.linalg.eigh(projected)
    keep = values > 1e-12
    root = vectors[:, keep] * np.sqrt(values[keep])
    location = design @ mean
    mode = np.zeros(root.shape[1])

    def likelihood(eta):
        rates = np.exp(eta)
        if dispersion is None:
            return (
                float(np.sum(goals * eta - rates - gammaln(goals + 1))),
                goals - rates,
                np.diag(rates),
            )
        pairs = rates.reshape(-1, 2)
        observed = goals.reshape(-1, 2)
        totals = observed.sum(axis=1) + dispersion
        log_denominator = logsumexp(
            np.column_stack([np.full(len(pairs), np.log(dispersion)), eta.reshape(-1, 2)]),
            axis=1,
        )
        shares = np.exp(eta.reshape(-1, 2) - log_denominator[:, None])
        gradient = (observed - totals[:, None] * shares).ravel()
        curvature = np.zeros((len(goals), len(goals)))
        for i, (share, total) in enumerate(zip(shares, totals, strict=True)):
            curvature[2 * i : 2 * i + 2, 2 * i : 2 * i + 2] = total * (
                np.diag(share) - np.outer(share, share)
            )
        logp = joint_logpmf(observed[:, 0], observed[:, 1], pairs[:, 0], pairs[:, 1], dispersion)
        return float(logp.sum()), gradient, curvature

    def objective(u):
        with np.errstate(over="ignore", invalid="ignore"):
            value = 0.5 * (u @ u) - likelihood(location + root @ u)[0]
        return value if np.isfinite(value) else np.inf

    for _ in range(60):
        logp, score, curvature = likelihood(location + root @ mode)
        gradient = mode - root.T @ score
        hessian = np.eye(len(mode)) + root.T @ curvature @ root
        step = cho_solve(cho_factor(hessian), gradient)
        if np.max(np.abs(gradient), initial=0) < 1e-8:
            break
        scale, old = 1.0, objective(mode)
        while objective(mode - scale * step) > old - 1e-4 * scale * (gradient @ step):
            scale *= 0.5
            if scale < 1e-10:
                if np.max(np.abs(step), initial=0) < 1e-7:
                    break
                raise RuntimeError("Score Laplace line search failed")
        mode -= scale * step
        if np.max(np.abs(scale * step), initial=0) < 1e-9:
            break
    else:
        raise RuntimeError("Score Laplace update did not converge")
    logp, score, curvature = likelihood(location + root @ mode)
    hessian = np.eye(len(mode)) + root.T @ curvature @ root
    mapping = cross @ (vectors[:, keep] / np.sqrt(values[keep]))
    posterior = (
        covariance
        + mapping
        @ (cho_solve(cho_factor(hessian), np.eye(len(mode))) - np.eye(len(mode)))
        @ mapping.T
    )
    evidence = logp - 0.5 * (mode @ mode) - 0.5 * np.linalg.slogdet(hessian)[1]
    return mean + mapping @ mode, (posterior + posterior.T) / 2, float(evidence)
