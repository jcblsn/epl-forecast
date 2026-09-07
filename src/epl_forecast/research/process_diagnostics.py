"""Known-state, observation calibration and availability checks for process models."""

from collections import defaultdict
from dataclasses import replace
from itertools import groupby

import numpy as np
from scipy.stats import poisson

from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.process_observation import ProcessObservation
from epl_forecast.models.process_quality_tilt import BayesianProcessQualityTilt
from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.models.xg_observation import ChanceObservation
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, BayesianXGQualityTilt
from epl_forecast.research.quality_tilt_reference import prepare


def conditional_goal_checks(observations, seed=801):
    rng = np.random.default_rng(seed)
    grouped = defaultdict(list)
    for row in observations:
        for side in ("home", "away"):
            grouped[row["match_date"][:4]].append((row[f"{side}_goals"], row[f"{side}_xg"]))
            grouped["overall"].append((row[f"{side}_goals"], row[f"{side}_xg"]))
    results = []
    for period, rows in sorted(grouped.items()):
        goals, xg = np.array(rows).T
        pits = poisson.cdf(goals - 1, xg) + rng.random(len(goals)) * poisson.pmf(goals, xg)
        expected_zero = np.exp(-xg)
        expected_tail = poisson.sf(3, xg)
        results.append(
            {
                "period": period,
                "team_matches": len(goals),
                "goal_mean": float(goals.mean()),
                "xg_mean": float(xg.mean()),
                "conditional_score_nll": float(-poisson.logpmf(goals, xg).mean()),
                "pearson_dispersion": float(np.mean((goals - xg) ** 2 / np.maximum(xg, 1e-12))),
                "zero_observed": float(np.mean(goals == 0)),
                "zero_expected": float(expected_zero.mean()),
                "zero_standardized_difference": float(
                    ((goals == 0) - expected_zero).sum()
                    / np.sqrt((expected_zero * (1 - expected_zero)).sum())
                ),
                "ge4_observed": float(np.mean(goals >= 4)),
                "ge4_expected": float(expected_tail.mean()),
                "pit_histogram": np.histogram(pits, np.linspace(0, 1, 11))[0].tolist(),
                "outside_central_90_percent": float(np.mean((pits < 0.05) | (pits > 0.95))),
            }
        )
    return {
        "seed": seed,
        "assumption": "M8 G|X ~ Poisson(X); realized xG diagnostic only",
        "results": results,
    }


def _generate(template, rng, regime):
    dimensions = template["design"].shape[-1]
    state = np.r_[np.log([1.2, 1.3]), np.zeros(dimensions - 2)]
    state += (
        rng.normal(size=dimensions)
        * np.r_[np.full(2, 0.25), np.full(dimensions - 2, 0.4 / np.sqrt(2))]
    )
    process = QualityTiltFilter(**XG_DYNAMICS)
    trajectory = [state.copy()]
    shock_index = len(template["dates"]) // 2
    for i, (years, active) in enumerate(zip(template["years"], template["active"], strict=True), 1):
        decay, variance = process.transition(years, dimensions)
        decay[2:] = np.where(active, decay[2:], 1)
        variance[2:] = np.where(active, variance[2:], 0)
        state = state * decay + rng.normal(size=dimensions) * np.sqrt(variance)
        if regime == "m8_shock" and i == shock_index:
            state[2] += 0.35
        trajectory.append(state.copy())
    trajectory = np.array(trajectory)
    eta = np.einsum("mij,mj->mi", template["design"], trajectory[template["day_index"]])
    q = np.exp(rng.normal(np.log(0.25), 0.35))
    if regime == "m7":
        goals, xg = ChanceObservation([], [], 0.2).sample(eta, rng)
    else:
        goals, xg = ProcessObservation([], [], q).sample(eta, rng)
    if regime == "provider_noise":
        xg *= rng.gamma(4, 0.25, size=xg.shape)
    matches, records = [], []
    for m, g, x in zip(template["matches"], goals, xg, strict=True):
        matches.append(replace(m, home_goals=int(g[0]), away_goals=int(g[1])))
        records.append(
            {
                "match_id": m.fixture.match_id,
                "provider": "understat",
                "match_date": str(m.fixture.match_date),
                "available_on": str(m.available_on),
                "home_goals": int(g[0]),
                "away_goals": int(g[1]),
                "home_xg": float(x[0]),
                "away_xg": float(x[1]),
            }
        )
    return matches, records, eta, trajectory[-1], template["dates"][shock_index], q


def known_state_checks(
    matches, replicates=30, seed=802, regimes=("m8", "m8_shock", "m7", "provider_noise")
):
    if replicates < 2:
        raise ValueError("At least two independent replicates are required")
    template = prepare(matches)
    rng = np.random.default_rng(seed)
    aggregates = defaultdict(list)
    scale_rows = []
    for regime in regimes:
        for replicate in range(replicates):
            generated, records, truth, final, shock_day, q = _generate(template, rng, regime)
            available = rng.random(len(records)) < 0.5
            models = {
                "M5-centered": CenteredQualityTiltFilter(**XG_DYNAMICS),
                "M7": BayesianXGQualityTilt(records),
                "M8-full": BayesianProcessQualityTilt(records),
                "M8-half": BayesianProcessQualityTilt(
                    [r for r, keep in zip(records, available, strict=True) if keep]
                ),
                "M8-none": BayesianProcessQualityTilt(),
            }
            indices = {m.fixture.match_id: i for i, m in enumerate(generated)}
            values = defaultdict(list)
            post = 0
            for day, group in groupby(generated, key=lambda m: m.fixture.match_date):
                games = list(group)
                prior = [m for m in generated if m.available_on <= day]
                if not prior:
                    continue
                for model in models.values():
                    model.fit(prior, day)
                for game in games:
                    i = indices[game.fixture.match_id]
                    tags = ["all"]
                    if template["teams"][0] in (
                        game.fixture.home_team_id,
                        game.fixture.away_team_id,
                    ):
                        if day >= shock_day:
                            post += 1
                        tags.append(
                            "pre_change"
                            if not post
                            else "first_three_after"
                            if post <= 3
                            else "later_after"
                        )
                    for name, model in models.items():
                        members = getattr(model, "members", [model])
                        weights = getattr(model, "weights", np.ones(1))
                        moments = [member.forecast_moments(game.fixture) for member in members]
                        means = np.array([m for m, _ in moments])
                        mean = weights @ means
                        variance = weights @ np.array([np.diag(c) for _, c in moments])
                        variance += weights @ (means - mean) ** 2
                        error = mean - truth[i]
                        for tag in tags:
                            values[name, tag, "mse"].extend(error**2)
                            values[name, tag, "coverage90"].extend(
                                np.abs(error) <= 1.644853626951 * np.sqrt(variance)
                            )
                            values[name, tag, "variance"].extend(variance)
            for name, model in models.items():
                model.fit(generated, template["cutoff"])
                members = getattr(model, "members", [model])
                weights = getattr(model, "weights", np.ones(1))
                n = len(template["teams"])
                transform = np.eye(2 + 2 * n)
                for offset in (2, 3):
                    ix = np.arange(offset, 2 + 2 * n, 2)
                    transform[np.ix_(ix, ix)] -= np.ones((n, n)) / n
                means, variances = [], []
                for member in members:
                    m, c = member.population_moments()
                    order = [0, 1] + [
                        2 + 2 * member.team_index[t] + d
                        for t in template["teams"]
                        for d in range(2)
                    ]
                    means.append(transform @ m[order])
                    variances.append(np.diag(transform @ c[np.ix_(order, order)] @ transform.T))
                mean = weights @ np.array(means)
                variance = weights @ np.array(variances) + weights @ (np.array(means) - mean) ** 2
                error = mean - transform @ final
                for label, ix in [
                    ("quality_contrasts", slice(2, None, 2)),
                    ("tilt_contrasts", slice(3, None, 2)),
                    ("league_home", slice(0, 2)),
                ]:
                    values[name, label, "coverage90"].extend(
                        np.abs(error[ix]) <= 1.644853626951 * np.sqrt(variance[ix])
                    )
                    values[name, label, "mse"].extend(error[ix] ** 2)
                if name == "M8-full":
                    scales = np.array([m.process_scale for m in members])
                    scale_rows.append(
                        {
                            "regime": regime,
                            "replicate": replicate,
                            "true_scale": q,
                            "posterior_mean": float(weights @ scales),
                            "edge_mass": float(weights[0] + weights[-1]),
                        }
                    )
            for (name, tag, measure), v in values.items():
                aggregates[regime, name, tag, measure].append(float(np.mean(v)))
            print(f"State diagnostic {regime} {replicate + 1}/{replicates}", flush=True)
    rows = []
    for (regime, name, tag, measure), v in sorted(aggregates.items()):
        rows.append(
            {
                "regime": regime,
                "model": name,
                "slice": tag,
                "measure": measure,
                "mean": float(np.mean(v)),
                "replicate_se": float(np.std(v, ddof=1) / np.sqrt(len(v))),
                "replicates": len(v),
            }
        )
    return {
        "seed": seed,
        "matches_per_replicate": len(matches),
        "results": rows,
        "process_scale": scale_rows,
        "scope": (
            "Fresh population priors; rate intervals use moment-matched Gaussian mixtures; "
            "no promotion bridge"
        ),
        "regimes": list(regimes),
        "quality_shock": 0.35,
        "provider_noise_cv": 0.5,
    }


def predictive_checks(matches, records, start, end, draws=2000, seed=803):
    rng = np.random.default_rng(seed)
    lookup = {r["match_id"]: r for r in records}
    target = sorted(
        [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and start <= m.fixture.match_date < end
        ],
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )
    models = {"M7": BayesianXGQualityTilt(records), "M8": BayesianProcessQualityTilt(records)}
    results = defaultdict(list)
    scales = []
    for day, group in groupby(target, key=lambda m: m.fixture.match_date):
        prior = [m for m in matches if m.available_on <= day]
        for name, model in models.items():
            model.fit(prior, day)
            if name == "M8":
                q = np.array([m.process_scale for m in model.members])
                scales.append(
                    {
                        "day": str(day),
                        "mean": float(model.weights @ q),
                        "sd": float(np.sqrt(model.weights @ (q - model.weights @ q) ** 2)),
                        "lower_edge_mass": float(model.weights[0]),
                        "upper_edge_mass": float(model.weights[-1]),
                    }
                )
        for match in group:
            row = lookup[match.fixture.match_id]
            observed_xg = np.array([row["home_xg"], row["away_xg"]])
            observed_goals = np.array([match.home_goals, match.away_goals])
            for name, model in models.items():
                member_ids = rng.choice(len(model.members), size=draws, p=model.weights)
                simulated_xg, simulated_goals = np.empty((draws, 2)), np.empty((draws, 2))
                for index, member in enumerate(model.members):
                    mask = member_ids == index
                    if not mask.any():
                        continue
                    mean, covariance = member.forecast_moments(match.fixture)
                    eta = rng.multivariate_normal(mean, covariance, size=int(mask.sum()))
                    likelihood = (
                        ProcessObservation([], [], member.process_scale)
                        if name == "M8"
                        else ChanceObservation([], [], member.chance_probability)
                    )
                    simulated_goals[mask], simulated_xg[mask] = likelihood.sample(eta, rng)
                for label, observed, simulated in [
                    ("xg", observed_xg, simulated_xg),
                    ("goals", observed_goals, simulated_goals),
                ]:
                    pit = (
                        np.sum(simulated < observed, axis=0)
                        + rng.random(2) * np.sum(simulated == observed, axis=0)
                    ) / draws
                    for season in (match.fixture.season_id, "overall"):
                        results[name, season, label].append(
                            {
                                "pit": pit.tolist(),
                                "observed_zero": (observed == 0).tolist(),
                                "predicted_zero": (simulated == 0).mean(axis=0).tolist(),
                                "observed_ge4": (observed >= 4).tolist(),
                                "predicted_ge4": (simulated >= 4).mean(axis=0).tolist(),
                                "bias": (simulated.mean(axis=0) - observed).tolist(),
                            }
                        )
    summary = []
    for (name, season, label), values in sorted(results.items()):
        pits = np.array([v["pit"] for v in values]).ravel()
        summary.append(
            {
                "model": name,
                "season": season,
                "observation": label,
                "team_matches": len(pits),
                "pit_histogram": np.histogram(pits, np.linspace(0, 1, 11))[0].tolist(),
                "central90_coverage": float(np.mean((pits >= 0.05) & (pits <= 0.95))),
                **{
                    key: float(np.mean([v[key] for v in values]))
                    for key in values[0]
                    if key != "pit"
                },
            }
        )
    sensitivity = []
    for day in sorted({m.fixture.match_date for m in target})[
        :: max(1, len({m.fixture.match_date for m in target}) // 3)
    ][:3]:
        prior = [m for m in matches if m.available_on <= day]
        fixture = next(m.fixture for m in target if m.fixture.match_date == day)
        comparisons = []
        for order in (5, 9):
            model = BayesianProcessQualityTilt(records, scale_order=order).fit(prior, day)
            q = np.array([m.process_scale for m in model.members])
            comparisons.append(
                {
                    "order": order,
                    "scale_mean": float(model.weights @ q),
                    "scale_sd": float(np.sqrt(model.weights @ (q - model.weights @ q) ** 2)),
                    "probabilities": list(model.predict_match(fixture).probabilities),
                }
            )
        sensitivity.append(
            {
                "day": str(day),
                "match_id": fixture.match_id,
                "comparison": comparisons,
                "max_probability_difference": float(
                    np.max(
                        np.abs(
                            np.array(comparisons[0]["probabilities"])
                            - comparisons[1]["probabilities"]
                        )
                    )
                ),
            }
        )
    return {
        "seed": seed,
        "draws_per_match": draws,
        "scope": "Chronological pre-match joint predictive sampling; target xG and goals excluded",
        "summary": summary,
        "scale_history": scales,
        "scale_quadrature_sensitivity": sensitivity,
    }
