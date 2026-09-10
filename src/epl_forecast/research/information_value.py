"""Chronological residual-information checks for correlated team observations."""

from collections import defaultdict
from itertools import combinations

import numpy as np

from epl_forecast.research.uncertainty_report import cluster_interval

SIGNALS = ("goals", "xg", "shots", "shots_on_target")
CONCEPTS = {
    "goals": "Realized scoring, a noisy observation of team scoring intensity.",
    "xg": "Chance-quality-weighted scoring opportunity; EPL only, with provider measurement noise.",
    "shots": "Shot volume, a potential sensor of attacking process rather than literal expected goals.",
    "shots_on_target": "On-target shot volume, overlapping with shots and goals; independent measurement noise is not assumed.",
}


def fit_residual_sensor(controls, sensors, target, penalty=0.01):
    controls, sensors, target = map(
        lambda x: np.asarray(x, dtype=float), (controls, sensors, target)
    )
    if (
        controls.ndim != 2
        or sensors.ndim != 2
        or target.shape != (len(controls),)
        or len(sensors) != len(controls)
        or len(target) < 2
    ):
        raise ValueError("Require aligned nonempty training controls, sensors and targets")
    if not all(np.isfinite(x).all() for x in (controls, sensors, target)):
        raise ValueError("Residual sensor fits require complete finite cases")
    center, scale = controls.mean(axis=0), controls.std(axis=0)
    scale = np.where(scale > 1e-10, scale, 1)
    design = np.column_stack((np.ones(len(target)), (controls - center) / scale))
    regularizer = np.eye(design.shape[1]) * penalty * len(target)
    regularizer[0, 0] = 0
    fit = np.linalg.solve(
        design.T @ design + regularizer, design.T @ np.column_stack((target, sensors))
    )
    residuals = np.column_stack((target, sensors)) - design @ fit
    sensor_scale = np.maximum(residuals[:, 1:].std(axis=0), 1e-8)
    z = residuals[:, 1:] / sensor_scale
    beta = (
        np.linalg.solve(z.T @ z + np.eye(z.shape[1]) * penalty * len(target), z.T @ residuals[:, 0])
        if z.shape[1]
        else np.empty(0)
    )
    baseline_variance = float(np.mean(residuals[:, 0] ** 2))
    variance = float(np.mean((residuals[:, 0] - z @ beta) ** 2))
    return {
        "center": center,
        "scale": scale,
        "fit": fit,
        "sensor_scale": sensor_scale,
        "beta": beta,
        "variance": max(variance, 1e-8),
        "baseline_variance": baseline_variance,
        "residuals": residuals,
    }


def predict_residual_sensor(fitted, controls, sensors):
    controls, sensors = np.asarray(controls, dtype=float), np.asarray(sensors, dtype=float)
    design = np.column_stack(
        (np.ones(len(controls)), (controls - fitted["center"]) / fitted["scale"])
    )
    baseline = design @ fitted["fit"]
    residual = (sensors - baseline[:, 1:]) / fitted["sensor_scale"]
    return baseline[:, 0] + residual @ fitted["beta"]


def information_report(rows, seed=20260910, signals_by_league=None):
    """Score every sensor subset chronologically.

    ``signals_by_league`` replaces the default goals/xG/shots/SOT set, so a focused
    study can ask about a few candidate signals without paying for the power set of
    every signal the archive happens to carry.
    """
    predictions, coefficients, residual_correlations = [], [], []
    residual_traces = defaultdict(list)
    for league in sorted({r["competition_id"] for r in rows}):
        signals = (
            (SIGNALS if league == "eng-premier-league" else tuple(s for s in SIGNALS if s != "xg"))
            if signals_by_league is None
            else tuple(signals_by_league[league])
        )
        complete = [
            r
            for r in rows
            if r["competition_id"] == league
            and all(r["signals"].get(s) is not None for s in signals)
        ]
        subsets = [group for n in range(len(signals) + 1) for group in combinations(signals, n)]
        for horizon in sorted({r["horizon"] for r in complete}):
            group = [r for r in complete if r["horizon"] == horizon]
            for season in sorted({r["season_id"] for r in group}):
                test = [r for r in group if r["season_id"] == season]
                cutoff = min(r["information_available_on"] for r in test)
                train = [
                    r
                    for r in group
                    if r["season_id"] < season and r["target_available_on"] < cutoff
                ]
                if len(train) < 300:
                    continue
                x, xt = (
                    np.array([r["controls"] for r in train]),
                    np.array([r["controls"] for r in test]),
                )
                y, yt = (
                    np.array([r["target"] for r in train]),
                    np.array([r["target"] for r in test]),
                )
                for subset in subsets:
                    sensors = np.array([[np.log1p(r["signals"][s]) for s in subset] for r in train])
                    test_sensors = np.array(
                        [[np.log1p(r["signals"][s]) for s in subset] for r in test]
                    )
                    fitted = fit_residual_sensor(x, sensors, y)
                    estimated = predict_residual_sensor(fitted, xt, test_sensors)
                    name = "+".join(subset) or "state_only"
                    base = {
                        "competition_id": league,
                        "season_id": season,
                        "horizon": horizon,
                        "sensors": name,
                    }
                    coefficients.append(
                        {
                            **base,
                            "training_rows": len(train),
                            "training_last_target_available_on": max(
                                r["target_available_on"] for r in train
                            ),
                            "test_first_information_available_on": cutoff,
                            "standardized_residual_coefficients": dict(
                                zip(subset, map(float, fitted["beta"]), strict=True)
                            ),
                            "training_conditional_variance_ratio": fitted["variance"]
                            / max(fitted["baseline_variance"], 1e-8),
                            "variance_scope": "Noisy future log1p-goals residual variance, not latent-state posterior covariance.",
                        }
                    )
                    if subset == signals:
                        covariance = np.cov(fitted["residuals"], rowvar=False)
                        denominator = np.sqrt(np.outer(np.diag(covariance), np.diag(covariance)))
                        correlation = np.divide(
                            covariance,
                            denominator,
                            out=np.full_like(covariance, np.nan),
                            where=denominator > 0,
                        )
                        residual_correlations.append(
                            {
                                **base,
                                "columns": ["future_goals_residual", *signals],
                                "correlation": [
                                    [float(v) if np.isfinite(v) else None for v in row]
                                    for row in correlation
                                ],
                            }
                        )
                        if horizon == 1:
                            design = np.column_stack(
                                (np.ones(len(test)), (xt - fitted["center"]) / fitted["scale"])
                            )
                            residual = (test_sensors - (design @ fitted["fit"])[:, 1:]) / fitted[
                                "sensor_scale"
                            ]
                            for row, values in zip(test, residual, strict=True):
                                residual_traces[league, season, row["team_id"]].append(
                                    (
                                        row["information_available_on"],
                                        row["match_id"],
                                        dict(zip(signals, values, strict=True)),
                                    )
                                )
                    sd = np.sqrt(fitted["variance"])
                    for row, actual, estimate in zip(test, yt, estimated, strict=True):
                        error = float(actual - estimate)
                        predictions.append(
                            {
                                **base,
                                "match_id": row["match_id"],
                                "team_id": row["team_id"],
                                "target_match_id": row["target_match_id"],
                                "information_available_on": row["information_available_on"],
                                "target_available_on": row["target_available_on"],
                                "squared_error": error**2,
                                "proxy_gaussian_nll": float(
                                    np.log(sd * np.sqrt(2 * np.pi)) + error**2 / (2 * sd**2)
                                ),
                                "proxy_coverage_90": int(abs(error) <= 1.6448536269514722 * sd),
                                "proxy_width_90": float(2 * 1.6448536269514722 * sd),
                            }
                        )
    grouped = defaultdict(dict)
    for row in predictions:
        key = row["competition_id"], row["horizon"], row["sensors"]
        grouped[key][row["season_id"], row["match_id"], row["team_id"]] = row
    comparisons, stability = [], []
    for (league, horizon, sensors), candidate in sorted(grouped.items()):
        if sensors == "state_only":
            continue
        members = sensors.split("+")
        comparators = {"state_only"} | {
            "+".join(s for s in members if s != removed) or "state_only" for removed in members
        }
        for comparator in sorted(comparators):
            baseline = grouped[league, horizon, comparator]
            if candidate.keys() != baseline.keys():
                raise ValueError("Information comparison requires identical complete cases")
            keys = sorted(candidate)
            delta = [candidate[k]["squared_error"] - baseline[k]["squared_error"] for k in keys]
            base = {
                "competition_id": league,
                "horizon": horizon,
                "candidate": sensors,
                "comparator": comparator,
            }
            comparisons.append({**base, **cluster_interval(delta, [k[0] for k in keys], seed)})
            for dimension in ("season_id", "team_id"):
                slices = defaultdict(list)
                for k, value in zip(keys, delta, strict=True):
                    slices[candidate[k][dimension]].append(value)
                stability.extend(
                    {
                        **base,
                        "dimension": dimension,
                        "value": value,
                        "rows": len(differences),
                        "mse_difference": float(np.mean(differences)),
                    }
                    for value, differences in sorted(slices.items())
                )
    persistence_pairs = defaultdict(list)
    for (league, _, _), trace in residual_traces.items():
        ordered = sorted(trace)
        for lag in (1, 3, 6):
            for left, right in zip(ordered, ordered[lag:], strict=False):
                for signal in left[2]:
                    persistence_pairs[league, signal, lag].append(
                        (left[2][signal], right[2][signal])
                    )
    persistence = []
    for (league, signal, lag), pairs in sorted(persistence_pairs.items()):
        values = np.asarray(pairs)
        correlation = (
            float(np.corrcoef(values.T)[0, 1])
            if len(values) > 1 and np.all(values.std(axis=0) > 0)
            else None
        )
        persistence.append(
            {
                "competition_id": league,
                "signal": signal,
                "lag_complete_case_team_matches": lag,
                "pairs": len(pairs),
                "residual_correlation": correlation,
                "scope": "Within team-season, using residual transforms fitted only on earlier seasons; gaps count retained complete-case matches.",
            }
        )
    uncertainty_groups = defaultdict(list)
    for row in rows:
        if row["horizon"] != 1 or "log_rate_posterior_variance" not in row:
            continue
        for observation, variance in row["log_rate_posterior_variance"].items():
            if observation != "before_observation" and variance is not None:
                uncertainty_groups[row["competition_id"], row["season_id"], observation].append(
                    variance / row["log_rate_posterior_variance"]["before_observation"]
                )
    posterior_uncertainty = [
        {
            "competition_id": league,
            "season_id": season,
            "observations": observation,
            "team_matches": len(ratios),
            "mean_posterior_to_prior_variance": float(np.mean(ratios)),
            "scope": "Single-match Laplace update of joint latent log scoring rates from the identical pre-match M7-member Gaussian prior. Includes opponent and league uncertainty; not a team-only posterior.",
        }
        for (league, season, observation), ratios in sorted(uncertainty_groups.items())
    ]
    return {
        "concepts": CONCEPTS,
        "comparisons": comparisons,
        "stability": stability,
        "coefficients": coefficients,
        "residual_correlations": residual_correlations,
        "persistence": persistence,
        "posterior_uncertainty": posterior_uncertainty,
        "unassimilated_sensors": "Shots and SOT have no admitted likelihood here; no latent posterior shrinkage is claimed for them. Conditional future-score variance is reported separately.",
        "predictions": predictions,
        "scope": "Chronological pooled residual diagnostic, conditional on pre-observation M7-parent state and fixture controls. All sensor subsets share league/horizon complete cases. Proxy predictive scores and intervals are not football score distributions or latent-state credible intervals. Shots/SOT are not yet assimilated into operational states.",
    }


def correlated_sensor_calibration(seed=20260910, draws=20000):
    rng = np.random.default_rng(seed)
    state = rng.normal(size=draws)
    noise = np.full((4, 4), 0.8) + np.eye(4) * 0.2
    observations = state[:, None] + rng.multivariate_normal(np.zeros(4), noise, size=draws)
    results = []
    for name, assumed in (
        ("joint_sensor_noise", noise),
        ("incorrect_independence", np.diag(np.diag(noise))),
    ):
        precision_loading = np.linalg.solve(assumed, np.ones(4))
        variance = 1 / (1 + precision_loading.sum())
        mean = observations @ precision_loading * variance
        results.append(
            {
                "assumption": name,
                "posterior_variance": float(variance),
                "known_state_coverage_90": float(
                    np.mean(np.abs(state - mean) <= 1.6448536269514722 * np.sqrt(variance))
                ),
                "state_mse": float(np.mean((state - mean) ** 2)),
            }
        )
    return {
        "seed": seed,
        "draws": draws,
        "results": results,
        "scope": "Known Gaussian state and correlated sensors: calibration check for information accounting, not a football observation-model validation.",
    }
