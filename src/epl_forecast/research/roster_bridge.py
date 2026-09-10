"""Known-minutes attacking roster deltas applied to fixed pre-match baselines."""

import math
from collections import defaultdict
from datetime import date

import numpy as np
from scipy.optimize import minimize

from epl_forecast.models.poisson import IndependentPoisson, PoissonMixture
from epl_forecast.research.player_prior import london_date

BASELINES = ("M2-attack-defense-v1", "M7-xg-v1")


def roster_delta(target, reference, players):
    """The same cutoff-specific player distribution appears on both sides."""
    ids = sorted(set(target) | set(reference))
    difference = np.array([target.get(pid, 0.0) - reference.get(pid, 0.0) for pid in ids])
    means = np.array([[t.mean for t in players[pid].traits] for pid in ids])
    variances = np.array([[t.variance for t in players[pid].traits] for pid in ids])
    return {
        "mean": difference @ means,
        "variance": difference**2 @ variances,
        "changed_match_equivalents": float(np.abs(difference).sum() / 2),
        "target_exposure": float(sum(target.values())),
        "reference_exposure": float(sum(reference.values())),
        "target_cold_exposure": float(
            sum(weight for pid, weight in target.items() if players[pid].traits[0].appearances == 0)
        ),
    }


def distribution(row, delta=(0.0, 0.0)):
    delta = np.asarray(delta)
    if row["model_id"] == BASELINES[0]:
        rates = np.array(
            [float(row["expected_home_goals"]), float(row["expected_away_goals"])]
        ) * np.exp(delta)
        return IndependentPoisson(*rates)
    if row["model_id"] != BASELINES[1] or not np.isclose(
        float(row["effective_specifications"]), 1.0, atol=1e-12, rtol=0
    ):
        raise ValueError("The retained M7 control requires one effective Gaussian specification")
    mean = np.array([float(row["log_home_rate_mean"]), float(row["log_away_rate_mean"])])
    cross = float(row["log_rate_covariance"])
    covariance = [
        [float(row["log_home_rate_variance"]), cross],
        [cross, float(row["log_away_rate_variance"])],
    ]
    return PoissonMixture(mean + delta, covariance)


def fit_mapping(cases, model_id, ridge=1.0):
    """Two coefficients, no intercept; baseline rate calibration stays fixed."""
    matrix = np.array([case[side]["mean"] for case in cases for side in ("home", "away")])
    response = np.array(
        [
            float(case["baselines"][model_id][f"{side}_goals"])
            for case in cases
            for side in ("home", "away")
        ]
    )
    offset = np.array(
        [
            math.log(float(case["baselines"][model_id][f"expected_{side}_goals"]))
            for case in cases
            for side in ("home", "away")
        ]
    )

    def objective(beta):
        eta = offset + matrix @ beta
        mean = np.exp(eta)
        return float(np.sum(mean - response * eta) + 0.5 * ridge * beta @ beta), matrix.T @ (
            mean - response
        ) + ridge * beta

    result = minimize(objective, np.zeros(2), jac=True, method="BFGS", options={"gtol": 1e-7})
    if not result.success and np.linalg.norm(result.jac) > 1e-4:
        raise RuntimeError(f"Roster mapping failed: {result.message}")
    mean = np.exp(offset + matrix @ result.x)
    hessian = (matrix.T * mean) @ matrix + ridge * np.eye(2)
    return {
        "beta": result.x,
        "covariance": np.linalg.inv(hessian),
        "training_fixtures": len(cases),
        "design_rank": int(np.linalg.matrix_rank(matrix)),
        "design_condition": float(np.linalg.cond(matrix)),
    }


def score_case(case, model_id, fit):
    row = case["baselines"][model_id]
    deltas = np.array([case[side]["mean"] @ fit["beta"] for side in ("home", "away")])
    output = []
    for variant, shift in (("baseline", np.zeros(2)), ("roster_delta", deltas)):
        scores = distribution(row, shift)
        probabilities = np.asarray(scores.outcome_probabilities())
        outcome = ("H", "D", "A").index(row["outcome"])
        target = np.eye(3)[outcome]
        output.append(
            {
                "match_id": row["match_id"],
                "season_id": row["season_id"],
                "match_date": row["match_date"],
                "forecast_as_of": row["forecast_as_of"],
                "model_id": model_id,
                "variant": variant,
                "score_nll": -scores.log_probability(
                    int(row["home_goals"]), int(row["away_goals"])
                ),
                "log_loss": -math.log(max(probabilities[outcome], 1e-15)),
                "brier": float(np.sum((probabilities - target) ** 2)),
                "p_home": float(probabilities[0]),
                "p_draw": float(probabilities[1]),
                "p_away": float(probabilities[2]),
                "home_log_delta": float(shift[0]),
                "away_log_delta": float(shift[1]),
                "home_goals": int(row["home_goals"]),
                "away_goals": int(row["away_goals"]),
                "home_rate": scores.home_rate,
                "away_rate": scores.away_rate,
                **case["slices"],
            }
        )
    return output


def chronological_bridge(cases, first_scored, minimum_training=200):
    cases = sorted(cases, key=lambda case: (case["cutoff"], case["match_id"]))
    predictions, mappings, skipped = [], [], []
    for cutoff in sorted({case["cutoff"] for case in cases if case["cutoff"] >= first_scored}):
        training = [case for case in cases if case["match_date"] < cutoff]
        targets = [case for case in cases if case["cutoff"] == cutoff]
        if len(training) < minimum_training:
            skipped.append(
                {"cutoff": str(cutoff), "training": len(training), "fixtures": len(targets)}
            )
            continue
        for model_id in BASELINES:
            fit = fit_mapping(training, model_id)
            mappings.append(
                {
                    "cutoff": str(cutoff),
                    "model_id": model_id,
                    **{
                        key: value.tolist() if isinstance(value, np.ndarray) else value
                        for key, value in fit.items()
                    },
                    "last_training_match": str(max(case["match_date"] for case in training)),
                }
            )
            for case in targets:
                predictions.extend(score_case(case, model_id, fit))
    return {"predictions": predictions, "mappings": mappings, "skipped": skipped}


def prepare_cases(
    baselines,
    appearances,
    portable,
    availability,
    reference_matches=8,
    minimum_reference=3,
    progress=None,
):
    """Actual target minutes are the only future information admitted as predictors."""
    by_match = defaultdict(dict)
    for row in baselines:
        if row["model_id"] in BASELINES:
            if row["model_id"] in by_match[row["match_id"]]:
                raise ValueError("Duplicate baseline fixture")
            by_match[row["match_id"]][row["model_id"]] = row
    rosters, dates, seasons, eligible_dates = defaultdict(dict), {}, {}, {}
    player_history, team_history = defaultdict(list), defaultdict(list)
    for row in appearances:
        if not row.get("minutes") or row["minutes"] <= 0:
            continue
        key = row["match_id"], row["team_id"]
        pid = row["player_id"]
        if pid in rosters[key]:
            raise ValueError("Duplicate appearance in oracle roster")
        day = london_date(row["kickoff_time"])
        eligible = (
            day
            if row["evidence_basis"] == "retrospective"
            else max(day, london_date(row["retrieved_at"]))
        )
        rosters[key][pid] = float(row["minutes"]) / 90.0
        dates[key] = day
        seasons[key] = row["season_id"]
        eligible_dates[key] = max(eligible_dates.get(key, eligible), eligible)
        player_history[pid].append((eligible, day, row["team_id"]))
    for key in rosters:
        team_history[key[1]].append(key)
    for history in team_history.values():
        history.sort(key=lambda key: (dates[key], key))
    for history in player_history.values():
        history.sort()
    injury_by_player = defaultdict(list)
    for row in availability:
        if (
            "injur" in (row.get("reason") or "").lower()
            or "illness" in (row.get("reason") or "").lower()
        ):
            injury_by_player[row["player_id"]].append(row)
    pl_seasons = defaultdict(set)
    for row in appearances:
        if row["competition_id"] == "eng-premier-league":
            pl_seasons[row["season_id"]].add(row["team_id"])
    prepared, excluded = [], []
    ordered = sorted(
        by_match.items(), key=lambda item: (next(iter(item[1].values()))["forecast_as_of"], item[0])
    )
    previous_cutoff, player_cache = None, {}
    for index, (match_id, rows) in enumerate(ordered):
        if set(rows) != set(BASELINES):
            excluded.append({"match_id": match_id, "reason": "missing baseline"})
            continue
        base = rows[BASELINES[0]]
        if any(
            rows[m][key] != base[key]
            for m in BASELINES
            for key in (
                "forecast_as_of",
                "home_team_id",
                "away_team_id",
                "home_goals",
                "away_goals",
                "match_date",
            )
        ):
            raise ValueError("Baseline fixture information does not match")
        cutoff, match_day = (
            date.fromisoformat(base["forecast_as_of"]),
            date.fromisoformat(base["match_date"]),
        )
        if cutoff != previous_cutoff:
            previous_cutoff, player_cache = cutoff, {}
        case = {
            "match_id": match_id,
            "match_date": match_day,
            "cutoff": cutoff,
            "baselines": rows,
            "slices": {
                "transfer": False,
                "injury": False,
                "large_lineup_change": False,
                "opening": False,
                "promoted": False,
            },
        }
        try:
            for side in ("home", "away"):
                team = base[f"{side}_team_id"]
                target = rosters.get((match_id, team))
                history = [key for key in team_history[team] if eligible_dates[key] < cutoff]
                reference_keys = history[-reference_matches:]
                if not target or len(reference_keys) < minimum_reference:
                    raise ValueError("missing target minutes or insufficient reference history")
                reference = defaultdict(float)
                for key in reference_keys:
                    for pid, exposure in rosters[key].items():
                        reference[pid] += exposure / len(reference_keys)
                for pid in set(target) | set(reference):
                    if pid not in player_cache:
                        player_cache[pid] = portable.freeze(pid, cutoff)
                block = roster_delta(target, reference, player_cache)
                block["reference_matches"] = len(reference_keys)
                block["reference_last_date"] = str(max(dates[key] for key in reference_keys))
                block["team_id"] = team
                case[side] = block
                case["slices"]["large_lineup_change"] |= block["changed_match_equivalents"] >= 2.0
                case["slices"]["opening"] |= (
                    sum(seasons[key] == base["season_id"] for key in history) < 5
                )
                year = int(base["season_id"][:4])
                prior_season = f"{year - 1}-{year}"
                case["slices"]["promoted"] |= (
                    bool(pl_seasons[prior_season]) and team not in pl_seasons[prior_season]
                )
                for pid in target:
                    past = [entry for entry in player_history[pid] if entry[0] < cutoff]
                    case["slices"]["transfer"] |= bool(past) and past[-1][2] != team
                for pid, weight in reference.items():
                    if weight - target.get(pid, 0) < 0.2:
                        continue
                    for injury in injury_by_player[pid]:
                        fixture_match = injury.get("match_id") == match_id
                        interval_match = (
                            injury.get("scope") == "interval"
                            and injury.get("start_date") is not None
                            and injury["start_date"] <= match_day
                            and (injury.get("end_date") is None or injury["end_date"] >= match_day)
                        )
                        case["slices"]["injury"] |= fixture_match or interval_match
            prepared.append(case)
        except ValueError as error:
            excluded.append({"match_id": match_id, "reason": str(error)})
        if progress is not None and index % 50 == 0:
            progress(index, len(ordered), len(prepared))
    return prepared, excluded


def design(cases, model_id):
    """Stacked team-match design, observed goals and fixed baseline log-rate offset."""
    matrix = np.array([case[side]["mean"] for case in cases for side in ("home", "away")])
    response = np.array(
        [
            float(case["baselines"][model_id][f"{side}_goals"])
            for case in cases
            for side in ("home", "away")
        ]
    )
    offset = np.array(
        [
            math.log(float(case["baselines"][model_id][f"expected_{side}_goals"]))
            for case in cases
            for side in ("home", "away")
        ]
    )
    change = np.array(
        [case[side]["changed_match_equivalents"] for case in cases for side in ("home", "away")]
    )
    return matrix, response, offset, change


def attainable_gain(matrix, response, offset, ridge=1.0):
    """The best in-sample Poisson log-likelihood this design can add to a fixed offset.

    No chronological mapping can beat a fit that already saw its own evaluation
    window, so a negligible value here rejects the representation rather than the
    coefficient estimates.
    """

    def objective(beta):
        eta = offset + matrix @ beta
        mean = np.exp(eta)
        return float(np.sum(mean - response * eta) + 0.5 * ridge * beta @ beta), matrix.T @ (
            mean - response
        ) + ridge * beta

    result = minimize(
        objective, np.zeros(matrix.shape[1]), jac=True, method="BFGS", options={"gtol": 1e-9}
    )
    if not result.success and np.linalg.norm(result.jac) > 1e-4:
        raise RuntimeError(f"Attainable-gain fit failed: {result.message}")

    def log_likelihood(beta):
        eta = offset + matrix @ beta
        return float(np.sum(response * eta - np.exp(eta)))

    mean = np.exp(offset + matrix @ result.x)
    hessian = (matrix.T * mean) @ matrix + ridge * np.eye(matrix.shape[1])
    return {
        "beta": result.x.tolist(),
        "standard_error": np.sqrt(np.diag(np.linalg.inv(hessian))).tolist(),
        "gain": log_likelihood(result.x) - log_likelihood(np.zeros(matrix.shape[1])),
        "team_matches": int(len(response)),
        "design_rank": int(np.linalg.matrix_rank(matrix)),
        "design_condition": float(np.linalg.cond(matrix)),
    }


def permuted_gain(matrix, response, offset, ridge=1.0, draws=400, seed=11):
    """Break the roster-to-fixture link while holding both margins fixed."""
    generator = np.random.default_rng(seed)
    observed = attainable_gain(matrix, response, offset, ridge)["gain"]
    null = np.array(
        [
            attainable_gain(matrix[generator.permutation(len(response))], response, offset, ridge)[
                "gain"
            ]
            for _ in range(draws)
        ]
    )
    return {
        "gain": observed,
        "draws": int(draws),
        "null_95th": float(np.quantile(null, 0.95)),
        "p_value": float(np.mean(null >= observed)),
    }


def representation_audit(cases, model_id, thresholds=(0.0, 3.0, 4.0, 5.0), draws=400, ridge=1.0):
    """Identification and representation check for a failed bridge mapping."""
    matrix, response, offset, change = design(cases, model_id)
    mean = np.exp(offset)
    residual = (response - mean) / np.sqrt(mean)
    strata = []
    for threshold in thresholds:
        mask = change >= threshold
        if mask.sum() <= matrix.shape[1]:
            continue
        strata.append(
            {
                "minimum_changed_match_equivalents": float(threshold),
                "share_of_team_matches": float(mask.mean()),
                **attainable_gain(matrix[mask], response[mask], offset[mask], ridge),
                **permuted_gain(matrix[mask], response[mask], offset[mask], ridge, draws),
                "residual_correlation": [
                    float(np.corrcoef(matrix[mask, column], residual[mask])[0, 1])
                    for column in range(matrix.shape[1])
                ],
            }
        )
    return {
        "model_id": model_id,
        "fixtures": int(len(cases)),
        "delta_mean": matrix.mean(axis=0).tolist(),
        "delta_sd": matrix.std(axis=0).tolist(),
        "changed_match_equivalents": {
            "median": float(np.median(change)),
            **{f"share_at_least_{t:g}": float((change >= t).mean()) for t in (2.0, 4.0, 6.0)},
        },
        "strata": strata,
    }
