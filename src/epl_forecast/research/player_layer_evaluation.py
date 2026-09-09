"""Chronological and cross-club evaluation of standalone player representations.

Every case conditions on the exposure the player actually went on to receive, so
the comparison isolates the process rate from lineup forecasting, which is outside
this batch. That makes the scores informative about the representation and
explicitly nondeployable as match forecasts.
"""

import math
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from epl_forecast.research.player_layer import (
    CANDIDATES,
    design,
    player_state,
)

DRAWS = 512
RIDGE = 1.0
EXPOSURE_BINS = (4.0, 8.0)
EVIDENCE_BINS = (5.0, 20.0)


def _bin(value, edges):
    return int(np.searchsorted(np.asarray(edges), value, side="right"))


def target_window(layer, player_id, cutoff, horizon_days, mark):
    """Realized exposure and process mark over the horizon, from eligible appearances."""
    indices = layer.by_player.get(player_id)
    if indices is None:
        return None
    start, end = cutoff.toordinal(), (cutoff + timedelta(days=horizon_days)).toordinal()
    selected = indices[(layer.days[indices] >= start) & (layer.days[indices] < end)]
    selected = selected[layer.available[mark][selected]]
    if not len(selected):
        return None
    clubs = []
    for index in selected:
        club = str(layer.teams[index])
        if club not in clubs:
            clubs.append(club)
    return {
        "exposure": float(layer.exposure[selected].sum()),
        "total": float(layer.values[mark][selected].sum()),
        "appearances": int(len(selected)),
        "clubs": clubs,
    }


def build_cases(layer, cutoffs, horizon_days, mark, minimum_exposure=2.0):
    cases = []
    for cutoff in cutoffs:
        day = cutoff.toordinal()
        for player_id, indices in layer.by_player.items():
            prior = indices[(layer.eligible[indices] <= day) & layer.available[mark][indices]]
            if not len(prior):
                continue
            outcome = target_window(layer, player_id, cutoff, horizon_days, mark)
            if outcome is None or outcome["exposure"] < minimum_exposure:
                continue
            state = player_state(layer, player_id, cutoff, target_club=outcome["clubs"][0])
            cases.append(
                {
                    "player_id": player_id,
                    "player_name": state.player_name,
                    "cutoff": cutoff,
                    "role": state.role,
                    "state": state,
                    "prior_exposure": float((layer.exposure[prior]).sum()),
                    "prior_effective_exposure": state.long[mark]["exposure"],
                    "club_before": state.club,
                    "club_after": outcome["clubs"][0],
                    "changed_club": state.club is not None and outcome["clubs"][0] != state.club,
                    "target_exposure": outcome["exposure"],
                    "target_total": outcome["total"],
                    "target_appearances": outcome["appearances"],
                }
            )
    return cases


def _matrix(cases, candidate, mark):
    names = None
    rows = []
    for case in cases:
        cached = case.setdefault("designs", {}).get(candidate)
        if cached is None:
            cached = design(case["state"], candidate, mark)
            case["designs"][candidate] = cached
        feature_names, values = cached
        if names is None:
            names = feature_names
        elif names != feature_names:
            raise ValueError("Inconsistent candidate design across cases")
        rows.append(values)
    matrix = np.array(rows).reshape(len(cases), len(names or []))
    return names or [], matrix


def _offset(cases, mark):
    values = []
    for case in cases:
        pool = case["state"].population[mark]
        rate = pool["by_role"].get(case["state"].role, pool["league"])
        values.append(math.log(max(rate, 1e-4)) + math.log(max(case["target_exposure"], 1e-6)))
    return np.array(values)


def fit_poisson_ridge(matrix, offset, response, ridge=RIDGE, iterations=60):
    """Ridge-penalised Poisson IRLS on standardised features; the intercept is free."""
    n, p = matrix.shape
    centre = matrix.mean(axis=0) if n else np.zeros(p)
    scale = matrix.std(axis=0) if n else np.ones(p)
    scale = np.where(scale > 1e-8, scale, 1.0)
    standardized = (matrix - centre) / scale if p else matrix
    designed = np.hstack([np.ones((n, 1)), standardized])
    penalty = np.eye(p + 1) * ridge
    penalty[0, 0] = 0.0
    beta = np.zeros(p + 1)
    for _ in range(iterations):
        eta = designed @ beta + offset
        mean = np.exp(np.clip(eta, -20, 20))
        weight = mean
        gradient = designed.T @ (response - mean) - penalty @ beta
        hessian = designed.T @ (designed * weight[:, None]) + penalty
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    eta = designed @ beta + offset
    mean = np.exp(np.clip(eta, -20, 20))
    dof = max(n - p - 1, 1)
    dispersion = float(((response - mean) ** 2 / np.maximum(mean, 1e-6)).sum() / dof)
    covariance = np.linalg.inv(designed.T @ (designed * mean[:, None]) + penalty) * max(
        dispersion, 1e-6
    )
    return {
        "beta": beta,
        "centre": centre,
        "scale": scale,
        "covariance": covariance,
        "dispersion": dispersion,
        "names": None,
    }


def _apply(model, matrix, offset):
    n, p = matrix.shape
    standardized = (matrix - model["centre"]) / model["scale"] if p else matrix
    designed = np.hstack([np.ones((n, 1)), standardized])
    eta = designed @ model["beta"] + offset
    variance = np.einsum("ij,jk,ik->i", designed, model["covariance"], designed)
    return np.exp(np.clip(eta, -20, 20)), np.sqrt(np.maximum(variance, 0.0))


def residual_pool(model, cases, matrix, offset, response):
    """Empirical multiplicative residuals, stratified by target exposure and evidence depth.

    Keeping the strata means a player with little retained evidence can receive a
    wider predictive distribution than an ever-present starter only if the retained
    outcomes actually justify it.
    """
    mean, _ = _apply(model, matrix, offset)
    pools = defaultdict(list)
    for case, expected, observed in zip(cases, mean, response, strict=True):
        if expected <= 0:
            continue
        key = (
            _bin(case["target_exposure"], EXPOSURE_BINS),
            _bin(case["prior_effective_exposure"], EVIDENCE_BINS),
        )
        pools[key].append(float(observed / expected))
        pools["all"].append(float(observed / expected))
    return {key: np.array(values) for key, values in pools.items() if len(values) >= 25} | {
        "all": np.array(pools["all"])
    }


def predictive_samples(pools, key, mean, parameter_sd, generator):
    ratios = pools.get(key, pools["all"])
    draws = generator.choice(ratios, size=DRAWS, replace=True)
    noise = generator.normal(0.0, parameter_sd, size=DRAWS) if parameter_sd > 0 else 0.0
    return mean * np.exp(noise) * draws


def crps(samples, observed):
    ordered = np.sort(samples)
    n = len(ordered)
    term = np.abs(ordered - observed).mean()
    index = np.arange(1, n + 1)
    spread = 2.0 * (ordered * (2 * index - n - 1)).sum() / (n * n)
    return float(term - 0.5 * spread)


def score_cases(model, pools, cases, matrix, offset, seed=0):
    generator = np.random.default_rng(seed)
    mean, parameter_sd = _apply(model, matrix, offset)
    results = []
    for case, expected, sd in zip(cases, mean, parameter_sd, strict=True):
        key = (
            _bin(case["target_exposure"], EXPOSURE_BINS),
            _bin(case["prior_effective_exposure"], EVIDENCE_BINS),
        )
        samples = predictive_samples(pools, key, expected, float(sd), generator)
        observed = case["target_total"]
        lower50, upper50 = np.quantile(samples, [0.25, 0.75])
        lower90, upper90 = np.quantile(samples, [0.05, 0.95])
        results.append(
            {
                "player_id": case["player_id"],
                "player_name": case["player_name"],
                "cutoff": str(case["cutoff"]),
                "role": case["role"],
                "changed_club": case["changed_club"],
                "club_before": case["club_before"],
                "club_after": case["club_after"],
                "prior_effective_exposure": case["prior_effective_exposure"],
                "target_exposure": case["target_exposure"],
                "observed": observed,
                "expected": float(expected),
                "parameter_sd": float(sd),
                "crps": crps(samples, observed),
                "absolute_error": float(abs(expected - observed)),
                "covered_50": bool(lower50 <= observed <= upper50),
                "covered_90": bool(lower90 <= observed <= upper90),
                "interval_width_90": float(upper90 - lower90),
            }
        )
    return results


def chronological_evaluation(layer, mark, cutoffs, horizon_days, first_scored, seed=0):
    """Expanding-window fit: a case may train only after its whole window has closed."""
    cases = build_cases(layer, cutoffs, horizon_days, mark)
    if not cases:
        return {"cases": 0, "scored": [], "candidates": {}}
    scored_cutoffs = sorted({c["cutoff"] for c in cases if c["cutoff"] >= first_scored})
    results = {name: [] for name in CANDIDATES}
    fitted, skipped = {}, []
    for cutoff in scored_cutoffs:
        closed = cutoff - timedelta(days=horizon_days)
        training = [c for c in cases if c["cutoff"] <= closed]
        evaluation = [c for c in cases if c["cutoff"] == cutoff]
        if len(training) < 200:
            skipped.append({"cutoff": str(cutoff), "training_cases": len(training)})
            continue
        for candidate in CANDIDATES:
            names, train_matrix = _matrix(training, candidate, mark)
            train_offset = _offset(training, mark)
            response = np.array([c["target_total"] for c in training])
            model = fit_poisson_ridge(train_matrix, train_offset, response)
            model["names"] = names
            pools = residual_pool(model, training, train_matrix, train_offset, response)
            _, evaluation_matrix = _matrix(evaluation, candidate, mark)
            scores = score_cases(
                model, pools, evaluation, evaluation_matrix, _offset(evaluation, mark), seed
            )
            results[candidate].extend(scores)
            fitted[candidate] = model
    return {
        "cases": len(cases),
        "scored": results,
        "models": fitted,
        "all_cases": cases,
        "scored_cutoffs": [str(c) for c in scored_cutoffs],
        "skipped_cutoffs": skipped,
    }


def summarize(scores):
    if not scores:
        return None
    return {
        "cases": len(scores),
        "players": len({s["player_id"] for s in scores}),
        "crps": float(np.mean([s["crps"] for s in scores])),
        "mae": float(np.mean([s["absolute_error"] for s in scores])),
        "coverage_50": float(np.mean([s["covered_50"] for s in scores])),
        "coverage_90": float(np.mean([s["covered_90"] for s in scores])),
        "mean_interval_width_90": float(np.mean([s["interval_width_90"] for s in scores])),
    }


def paired_bootstrap(left, right, draws=2000, seed=1):
    """Cluster the resample by player so one ever-present player is not many cases."""
    index = {(s["player_id"], s["cutoff"]): s for s in right}
    pairs = defaultdict(list)
    for score in left:
        other = index.get((score["player_id"], score["cutoff"]))
        if other is not None:
            pairs[score["player_id"]].append(score["crps"] - other["crps"])
    players = sorted(pairs)
    if len(players) < 5:
        return None
    values = [np.array(pairs[p]) for p in players]
    weights = np.array([len(v) for v in values], dtype=float)
    observed = float(np.concatenate(values).mean())
    generator = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        picked = generator.integers(0, len(players), size=len(players))
        total = sum(values[i].sum() for i in picked)
        count = weights[picked].sum()
        samples.append(total / count)
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return {
        "difference": observed,
        "interval": [float(lower), float(upper)],
        "players": len(players),
        "cases": int(weights.sum()),
    }


def transfer_episodes(layer, mark, minimum_prior=8.0, minimum_target=4.0, horizon_days=240):
    """Observed club changes used retrospectively as portability labels.

    A club switch here is evidence that the player later appeared for a different
    club, not a claim that a transfer was known to a forecaster at the cutoff.
    """
    episodes = []
    for player_id, indices in layer.by_player.items():
        usable = indices[layer.available[mark][indices]]
        if len(usable) < 5:
            continue
        teams = layer.teams[usable]
        changes = np.flatnonzero(teams[1:] != teams[:-1]) + 1
        for position in changes:
            first = usable[position]
            cutoff = date.fromordinal(int(layer.days[first]))
            before = usable[:position]
            before = before[layer.eligible[before] <= cutoff.toordinal()]
            if not len(before):
                continue
            prior_exposure = float(layer.exposure[before].sum())
            window = usable[position:]
            window = window[
                (layer.days[window] < cutoff.toordinal() + horizon_days)
                & (layer.teams[window] == teams[position])
            ]
            target_exposure = float(layer.exposure[window].sum())
            if prior_exposure < minimum_prior or target_exposure < minimum_target:
                continue
            state = player_state(layer, player_id, cutoff, target_club=str(teams[position]))
            episodes.append(
                {
                    "player_id": player_id,
                    "player_name": state.player_name,
                    "cutoff": cutoff,
                    "role": state.role,
                    "state": state,
                    "club_before": str(teams[position - 1]),
                    "club_after": str(teams[position]),
                    "changed_club": True,
                    "prior_exposure": prior_exposure,
                    "prior_effective_exposure": state.long[mark]["exposure"],
                    "target_exposure": target_exposure,
                    "target_total": float(layer.values[mark][window].sum()),
                    "target_appearances": int(len(window)),
                }
            )
    return episodes


def evaluate_transfers(layer, mark, episodes, training_cases, horizon_days=90, seed=0):
    """Fit on chronological cases whose windows closed before the move, then score it.

    The estimate is frozen at the day of the first appearance for the new club, so
    no evidence from that club reaches the prediction it is scored against.
    """
    buckets = defaultdict(list)
    for episode in episodes:
        buckets[episode["cutoff"].replace(day=1)].append(episode)
    results = {name: [] for name in CANDIDATES}
    for origin, group in sorted(buckets.items()):
        closed = origin - timedelta(days=horizon_days)
        training = [c for c in training_cases if c["cutoff"] <= closed]
        if len(training) < 200:
            continue
        offset = _offset(training, mark)
        response = np.array([c["target_total"] for c in training])
        for candidate in CANDIDATES:
            names, matrix = _matrix(training, candidate, mark)
            model = fit_poisson_ridge(matrix, offset, response)
            model["names"] = names
            pools = residual_pool(model, training, matrix, offset, response)
            _, episode_matrix = _matrix(group, candidate, mark)
            results[candidate].extend(
                score_cases(model, pools, group, episode_matrix, _offset(group, mark), seed)
            )
    return results
