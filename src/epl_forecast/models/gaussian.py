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
