"""Pooled cross-division initialization from correlated season observations."""

from collections import defaultdict
from datetime import date

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.linalg import cho_factor, cho_solve
from scipy.special import logsumexp

from epl_forecast.models.promotion import (
    CHAMPIONSHIP,
    PL,
    TeamPrior,
    completed_seasons,
    promotion_cohort,
)
from epl_forecast.models.quality_tilt import QT_FROM_AD


def replace_entry_priors(forecast, priors):
    """Replace entry marginals, retaining incumbent and global-state moments."""
    for team, prior in priors.items():
        index = 2 + 2 * forecast.team_index[team]
        block = slice(index, index + 2)
        forecast.mean[block] = QT_FROM_AD @ prior.mean
        forecast.covariance[block, :] = 0
        forecast.covariance[:, block] = 0
        forecast.covariance[block, block] = QT_FROM_AD @ prior.covariance @ QT_FROM_AD.T
    return forecast


def championship_observations(data):
    records = {
        (r["match_id"], r["team_id"]): r
        for r in data.rows("SELECT * FROM team_process WHERE provider='football_data'")
    }
    groups = defaultdict(list)
    for match in data.matches():
        f = match.fixture
        if f.competition_id != CHAMPIONSHIP or int(f.season_id[:4]) < 2013:
            continue
        sides = [records.get((f.match_id, team), {}) for team in (f.home_team_id, f.away_team_id)]
        if any(s.get(key) is None for s in sides for key in ("shots", "shots_on_target")):
            continue
        groups[f.season_id].append(
            (
                match,
                np.array(
                    [
                        [match.home_goals, sides[0]["shots"], sides[0]["shots_on_target"]],
                        [match.away_goals, sides[1]["shots"], sides[1]["shots_on_target"]],
                    ],
                    dtype=float,
                ),
            )
        )
    result = {}
    for season, games in sorted(groups.items()):
        averages = np.mean([counts for _, counts in games], axis=0)
        teams = defaultdict(list)
        for match, counts in games:
            f = match.fixture
            teams[f.home_team_id].append(counts / averages)
            teams[f.away_team_id].append((counts / averages)[::-1])
        for team, values in teams.items():
            if len(values) < 40:
                continue
            values = np.asarray(values)
            average = values.mean(axis=0)
            if np.any(average <= 0):
                continue
            mean = np.log(average) * np.array([[1], [-1]])
            covariances = [
                np.cov(values[:, side, :], rowvar=False, ddof=1)
                / (len(values) * np.outer(average[side], average[side]))
                for side in (0, 1)
            ]
            result[season, team] = {
                "mean": mean.tolist(),
                "covariance": np.array(covariances).tolist(),
                "matches": len(values),
                "available_on": str(max(m.available_on for m, _ in games)),
                "definition": "Home/division-adjusted goal, shot and SOT season log ratios; noisy state observations, not Championship xG.",
            }
    return result


def transition_cohorts(matches, sources):
    seasons = completed_seasons(matches, max(m.available_on for m in matches))
    result = []
    for (competition, season), premier in sorted(seasons.items()):
        if competition != PL:
            continue
        year = int(season[:4])
        source_season = f"{year - 1}-{year}"
        champ = seasons.get((CHAMPIONSHIP, source_season))
        if champ is None:
            continue
        for target in promotion_cohort(champ, premier):
            source = sources.get((source_season, target["team_id"]))
            if source is not None:
                result.append({**target, "source_season": source_season, "source": source})
    return result


def fit_transition(rows, dimension, signals):
    columns = (0,) if signals == "results" else (0, 1, 2) if signals == "process" else ()
    if signals not in {"population", "results", "process"}:
        raise ValueError("Unknown transition observations")
    if len(rows) < 6:
        raise ValueError("At least six earlier promoted cohorts are required")
    side = {"attack": 0, "defense": 1}[dimension]
    x = np.array([[1.0, *np.asarray(r["source"]["mean"])[side, list(columns)]] for r in rows])
    input_covariance = np.array(
        [np.asarray(r["source"]["covariance"])[side][np.ix_(columns, columns)] for r in rows]
    )
    y = np.array([r[f"entry_{dimension}"] for r in rows])
    yv = np.array([r[f"entry_{dimension}_variance"] for r in rows])
    prior_covariance = np.diag([0.6**2] + [0.5**2] * len(columns))
    nodes, weights = leggauss(41)
    scales = (nodes + 1) * 0.75
    input_noise = np.zeros(len(rows))
    for _ in range(4):
        means, covariances, log_weights = [], [], []
        for scale, weight in zip(scales, weights, strict=True):
            variance = yv + input_noise + scale**2
            marginal = np.diag(variance) + x @ prior_covariance @ x.T
            factor = cho_factor(marginal)
            log_weights.append(
                np.log(weight)
                - np.log(np.diag(factor[0])).sum()
                - 0.5 * (y @ cho_solve(factor, y))
                - 0.5 * (scale / 0.3) ** 2
            )
            covariance = np.linalg.inv(np.linalg.inv(prior_covariance) + (x.T / variance) @ x)
            covariances.append(covariance)
            means.append(covariance @ (x.T @ (y / variance)))
        probabilities = np.exp(np.array(log_weights) - logsumexp(log_weights))
        means = np.asarray(means)
        beta = probabilities @ means
        deviations = means - beta
        covariance = (
            np.einsum("i,ijk->jk", probabilities, covariances)
            + (deviations.T * probabilities) @ deviations
        )
        input_noise = np.einsum(
            "nij,ij->n", input_covariance, np.outer(beta[1:], beta[1:]) + covariance[1:, 1:]
        )
    return {
        "columns": columns,
        "coefficients": beta,
        "coefficient_covariance": covariance,
        "transition_variance": float(probabilities @ scales**2),
        "transition_sd_interval_05_95": np.interp(
            [0.05, 0.95], np.cumsum(probabilities), scales
        ).tolist(),
    }


def promotion_prior(cohorts, source, as_of, target_season, signals):
    eligible = [
        r
        for r in cohorts
        if r["season_id"] < target_season and date.fromisoformat(r["available_on"]) <= as_of
    ]
    if date.fromisoformat(source["available_on"]) > as_of:
        raise ValueError("Championship observations postdate entry cutoff")
    means, variances, diagnostics = [], [], []
    for side, dimension in enumerate(("attack", "defense")):
        fitted = fit_transition(eligible, dimension, signals)
        columns = fitted["columns"]
        x = np.r_[1.0, np.asarray(source["mean"])[side, list(columns)]]
        covariance = np.asarray(source["covariance"])[side][np.ix_(columns, columns)]
        beta, beta_covariance = fitted["coefficients"], fitted["coefficient_covariance"]
        mean = float(x @ beta)
        variance = float(
            fitted["transition_variance"]
            + x @ beta_covariance @ x
            + np.sum(covariance * (np.outer(beta[1:], beta[1:]) + beta_covariance[1:, 1:]))
        )
        means.append(mean)
        variances.append(variance)
        diagnostics.append(
            {
                "dimension": dimension,
                "coefficients": beta.tolist(),
                "coefficient_sd": np.sqrt(np.diag(beta_covariance)).tolist(),
                "transition_variance": fitted["transition_variance"],
                "transition_sd_interval_05_95": fitted["transition_sd_interval_05_95"],
                "mean_change_from_championship_goals": mean - source["mean"][side][0],
            }
        )
    return TeamPrior(
        np.array(means), np.diag(variances), f"pooled {signals} promotion transition"
    ), {
        "training_cohorts": len(eligible),
        "last_training_season": max(r["season_id"] for r in eligible),
        "dimensions": diagnostics,
        "covariance_scope": "Correlated goals/shots/SOT sampling noise within each dimension; attack/defense transition covariance not estimated from this small population.",
    }
